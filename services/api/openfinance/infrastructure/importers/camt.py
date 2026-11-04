"""Lector de CAMT.053 (extracto de cuenta de ISO 20022) (OF-1104).

Es XML y se lee **solo con defusedxml**: sin DTD, sin entidades externas y sin expansión de
entidades. Los nombres de etiqueta se comparan sin espacio de nombres, así que valen todas las
versiones (``camt.053.001.02``, ``.08``…).

- Una entrada (``Ntry``) puede traer varios movimientos (``TxDtls``) con su importe cada uno: se
  importa uno por cada ``TxDtls`` con importe. Sin ellos, la entrada entera es un movimiento.
- Débito = sale dinero (negativo); crédito = entra. Una anulación (``RvslInd``) invierte el signo.
- Solo se importa lo contabilizado (``BOOK``); lo pendiente se descarta con su motivo.
- Un archivo con extractos de cuentas distintas se rechaza.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

from openfinance.domain.imports import (
    ClassificationRules,
    ImportedRow,
    ParseResult,
    SkippedRow,
    fingerprint,
    suggest_kind,
)
from openfinance.domain.shared import Money
from openfinance.infrastructure.importers.common import (
    INVALID_AMOUNT,
    MAX_ROWS,
    ZERO_AMOUNT,
    ImportFormatError,
    to_decimal,
)

_MAX_DESCRIPTION = 500
_MAX_BYTES_SNIFF = 4096


def looks_like_camt(text: str) -> bool:
    head = text[:_MAX_BYTES_SNIFF].lower()
    return "<document" in head and "camt.053" in head


def _name(el: Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _children(el: Element | None, name: str) -> list[Element]:
    return [c for c in el if _name(c) == name] if el is not None else []


def _child(el: Element | None, *path: str) -> Element | None:
    for name in path:
        if el is None:
            return None
        found = _children(el, name)
        el = found[0] if found else None
    return el


def _text(el: Element | None, *path: str) -> str:
    node = _child(el, *path)
    return (node.text or "").strip() if node is not None else ""


def _date(el: Element | None) -> datetime | None:
    """``<Dt>2026-10-03</Dt>`` o ``<DtTm>2026-10-03T10:15:00+02:00</DtTm>``, como hora local."""
    if el is None:
        return None
    for tag in ("DtTm", "Dt"):
        value = _text(el, tag)
        if value:
            try:
                return datetime.strptime(value[:19].replace("T", " ").strip(), "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
            except ValueError:
                pass
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d")  # noqa: DTZ007 - fecha local
            except ValueError:
                return None
    return None


def _description(entry: Element, tx: Element | None, debit: bool) -> str:
    party_tag = "Cdtr" if debit else "Dbtr"
    scope = tx if tx is not None else entry
    party = _text(_child(scope, "RltdPties", party_tag), "Nm") or _text(
        _child(scope, "RltdPties", party_tag, "Pty"), "Nm"
    )
    remittance = " ".join(
        (u.text or "").strip()
        for u in _children(_child(scope, "RmtInf"), "Ustrd")
        if (u.text or "").strip()
    )
    extra = _text(tx, "AddtlTxInf") or _text(entry, "AddtlNtryInf")
    text = " ".join(p for p in (party, remittance or extra) if p)
    return " ".join(text.split())[:_MAX_DESCRIPTION]


def _reference(entry: Element, tx: Element | None) -> str:
    return (
        _text(tx, "Refs", "EndToEndId")
        or _text(tx, "Refs", "AcctSvcrRef")
        or _text(entry, "AcctSvcrRef")
    )


def parse_camt053(content: bytes, account_key: str, rules: ClassificationRules) -> ParseResult:
    try:
        root = fromstring(content, forbid_dtd=True)
    except (DefusedXmlException, ParseError) as exc:
        raise ImportFormatError("El XML no es válido o usa construcciones no permitidas") from exc
    if _name(root) != "Document" or _child(root, "BkToCstmrStmt") is None:
        raise ImportFormatError("No parece un extracto CAMT.053 (falta BkToCstmrStmt)")
    statements = _children(_child(root, "BkToCstmrStmt"), "Stmt")
    if not statements:
        raise ImportFormatError("El CAMT.053 no trae ningún extracto (Stmt)")
    accounts = {
        _text(s, "Acct", "Id", "IBAN") or _text(s, "Acct", "Id", "Othr", "Id") for s in statements
    }
    if len(accounts) > 1:
        raise ImportFormatError("El archivo trae extractos de cuentas distintas: exporta una sola")

    result = ParseResult()
    seen: dict[str, int] = {}
    dated: list[tuple[datetime, int, ImportedRow]] = []
    line = 0
    closing: tuple[Money, datetime | None] | None = None

    for stmt in statements:
        default_currency = _text(stmt, "Acct", "Ccy") or rules.currency
        for bal in _children(stmt, "Bal"):
            if _text(bal, "Tp", "CdOrPrtry", "Cd") != "CLBD":
                continue
            amt = _child(bal, "Amt")
            try:
                value = to_decimal(
                    amt.text.strip() if amt is not None and amt.text else "", decimal_sep="."
                )
            except ValueError:
                continue
            if amt is not None:
                signed = -value if _text(bal, "CdtDbtInd") == "DBIT" else value
                closing = (
                    Money.of(signed, amt.get("Ccy") or default_currency),
                    _date(_child(bal, "Dt")),
                )
        for entry in _children(stmt, "Ntry"):
            line += 1
            if line > MAX_ROWS:
                raise ImportFormatError(
                    f"El archivo tiene demasiados movimientos (máximo {MAX_ROWS})"
                )
            status = _text(entry, "Sts", "Cd") or _text(entry, "Sts")
            debit = _text(entry, "CdtDbtInd") == "DBIT"
            reversal = _text(entry, "RvslInd").lower() == "true"
            booked_at = _date(_child(entry, "BookgDt")) or _date(_child(entry, "ValDt"))
            details = [tx for nd in _children(entry, "NtryDtls") for tx in _children(nd, "TxDtls")]
            with_amount = [tx for tx in details if _child(tx, "Amt") is not None]
            parts: list[tuple[Element | None, Element | None]] = (
                [(tx, _child(tx, "Amt")) for tx in with_amount]
                if len(with_amount) > 1
                else [(details[0] if details else None, _child(entry, "Amt"))]
            )
            for tx, amt_el in parts:
                description = _description(entry, tx, debit)
                if status and status != "BOOK":
                    result.skipped.append(
                        SkippedRow(
                            line, "pendiente: se importará cuando se contabilice", description
                        )
                    )
                    continue
                if booked_at is None:
                    result.skipped.append(
                        SkippedRow(line, "fila no válida: fecha no válida", description)
                    )
                    continue
                try:
                    magnitude = to_decimal(
                        amt_el.text.strip() if amt_el is not None and amt_el.text else "",
                        decimal_sep=".",
                    )
                    if magnitude < 0:
                        raise ValueError("importe no válido")
                    negative = debit != reversal
                    amount = Money.of(
                        -magnitude if negative else magnitude,
                        (amt_el.get("Ccy") if amt_el is not None else None) or default_currency,
                    )
                except (ValueError, AttributeError):
                    result.skipped.append(SkippedRow(line, INVALID_AMOUNT, description))
                    continue
                if amount.is_zero:
                    result.skipped.append(SkippedRow(line, ZERO_AMOUNT, description))
                    continue
                reference = _reference(entry, tx)
                base = f"{booked_at.isoformat()}|{amount.amount}|{description}|{reference}"
                occurrence = seen.get(base, 0)
                seen[base] = occurrence + 1
                kind, member = suggest_kind(description, amount.amount > Decimal(0), rules)
                dated.append(
                    (
                        booked_at,
                        line,
                        ImportedRow(
                            booked_at=booked_at,
                            value_date=(_date(_child(entry, "ValDt")) or booked_at).date(),
                            description=description or "Movimiento sin concepto",
                            amount=amount,
                            bank_type=(_text(entry, "BkTxCd", "Domn", "Cd"))[:40],
                            suggested_kind=kind,
                            fingerprint=fingerprint(
                                account_key,
                                booked_at,
                                amount,
                                description,
                                occurrence,
                                discriminator=f"ref:{reference}" if reference else "",
                            ),
                            member=member,
                            line=line,
                        ),
                    )
                )
    dated.sort(key=lambda d: (d[0], d[1]))
    result.rows = [row for _, _, row in dated]
    if closing and result.rows:
        balance, as_of = closing
        last = result.rows[-1]
        if as_of is None or as_of.date() >= last.booked_at.date():
            result.rows[-1] = ImportedRow(
                booked_at=last.booked_at,
                value_date=last.value_date,
                description=last.description,
                amount=last.amount,
                bank_type=last.bank_type,
                suggested_kind=last.suggested_kind,
                fingerprint=last.fingerprint,
                member=last.member,
                balance_after=balance,
                line=last.line,
            )
    return result
