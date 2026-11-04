"""Lector de OFX (Open Financial Exchange), versiones 1 (SGML) y 2 (XML) (OF-1103).

No se usa un analizador XML: la versión 1 no cierra las etiquetas. Se buscan los bloques
``<STMTTRN>`` y, dentro, ``<ETIQUETA>valor``. Por eso un OFX malicioso no puede pedir entidades
externas ni expandirlas: aquí no existen.

Un archivo con más de una cuenta (varios ``<STMTRS>``) se rechaza: cada importación es de una
sola cuenta. El importe no pasa nunca por ``float``.
"""

from __future__ import annotations

import re
from datetime import datetime

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
    MISSING_AMOUNT,
    ZERO_AMOUNT,
    ImportFormatError,
    decode_text,
    to_decimal,
)

_BLOCK = re.compile(
    r"<STMTTRN>(.*?)(?=</STMTTRN>|<STMTTRN>|</BANKTRANLIST>|</?[A-Z]*STMTRS>|\Z)", re.S | re.I
)
_TAG = re.compile(r"<([A-Za-z][A-Za-z0-9.]*)>([^<\r\n]*)")
_MAX_DESCRIPTION = 500
_STATEMENTS = re.compile(r"<(?:CC)?STMTRS>", re.I)


def _fields(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag, value in _TAG.findall(block):
        out.setdefault(tag.upper(), value.strip())
    return out


def _date(value: str) -> datetime:
    """``AAAAMMDD`` con hora opcional (``AAAAMMDDHHMMSS[.xxx][zona]``); se toma como hora local."""
    digits = re.match(r"\d{8}(\d{6})?", value)
    if digits is None:
        raise ValueError("fecha no válida")
    text = digits.group(0)
    fmt = "%Y%m%d%H%M%S" if len(text) == 14 else "%Y%m%d"
    return datetime.strptime(text, fmt)  # noqa: DTZ007 - fecha local del banco


def _description(fields: dict[str, str]) -> str:
    name, memo = fields.get("NAME", ""), fields.get("MEMO", "")
    if name and memo and memo.casefold() != name.casefold():
        return f"{name} {memo}"[:_MAX_DESCRIPTION]
    return (name or memo)[:_MAX_DESCRIPTION]


def looks_like_ofx(text: str) -> bool:
    head = text[:4096].lstrip().lower()
    return head.startswith("ofxheader") or "<ofx>" in head or "<ofx " in head


def parse_ofx(content: bytes, account_key: str, rules: ClassificationRules) -> ParseResult:
    text = decode_text(content)
    if not looks_like_ofx(text):
        raise ImportFormatError("No parece un archivo OFX")
    if len(_STATEMENTS.findall(text)) > 1:
        raise ImportFormatError("El archivo OFX trae más de una cuenta: exporta una sola")
    currency_match = re.search(r"<CURDEF>\s*([A-Za-z]{3})", text)
    if currency_match is None:
        raise ImportFormatError("El OFX no indica la moneda (CURDEF)")
    currency = currency_match.group(1).upper()
    blocks = _BLOCK.findall(text)
    if len(blocks) > MAX_ROWS:
        raise ImportFormatError(f"El archivo tiene demasiados movimientos (máximo {MAX_ROWS})")
    if not blocks and "<STMTTRN" not in text.upper():
        raise ImportFormatError("El OFX no trae movimientos (<STMTTRN>)")

    result = ParseResult()
    seen: dict[str, int] = {}
    dated: list[tuple[datetime, int, ImportedRow]] = []
    for line, block in enumerate(blocks, start=1):
        f = _fields(block)
        description = _description(f)
        try:
            booked_at = _date(f.get("DTPOSTED", ""))
        except ValueError:
            result.skipped.append(SkippedRow(line, "fila no válida: fecha no válida", description))
            continue
        raw = f.get("TRNAMT", "")
        if not raw:
            result.skipped.append(SkippedRow(line, MISSING_AMOUNT, description))
            continue
        try:
            amount = Money.of(to_decimal(raw), currency)
        except ValueError:
            result.skipped.append(SkippedRow(line, INVALID_AMOUNT, description))
            continue
        if amount.is_zero:
            result.skipped.append(SkippedRow(line, ZERO_AMOUNT, description))
            continue
        fitid = f.get("FITID", "")
        base = f"{booked_at.isoformat()}|{amount.amount}|{description}|{fitid}"
        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        kind, member = suggest_kind(description, amount.amount > 0, rules)
        dated.append(
            (
                booked_at,
                line,
                ImportedRow(
                    booked_at=booked_at,
                    value_date=booked_at.date(),
                    description=description or "Movimiento sin concepto",
                    amount=amount,
                    bank_type=f.get("TRNTYPE", "")[:40],
                    suggested_kind=kind,
                    fingerprint=fingerprint(
                        account_key,
                        booked_at,
                        amount,
                        description,
                        occurrence,
                        discriminator=f"fitid:{fitid}" if fitid else "",
                    ),
                    member=member,
                    line=line,
                ),
            )
        )
    dated.sort(key=lambda d: (d[0], d[1]))
    result.rows = [row for _, _, row in dated]

    ledger = re.search(r"<LEDGERBAL>(.*?)(?:</LEDGERBAL>|</?[A-Z]+STMTRS>|\Z)", text, re.S | re.I)
    if ledger and result.rows:
        lf = _fields(ledger.group(1))
        try:
            balance = Money.of(to_decimal(lf.get("BALAMT", "")), currency)
            as_of = _date(lf["DTASOF"]) if "DTASOF" in lf else None
        except (ValueError, KeyError):
            balance, as_of = None, None
        last = result.rows[-1]
        # El saldo del banco es el de tras el último movimiento si es de esa fecha o posterior.
        if balance is not None and (as_of is None or as_of.date() >= last.booked_at.date()):
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
