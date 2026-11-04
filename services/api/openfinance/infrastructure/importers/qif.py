"""Lector de QIF (Quicken Interchange Format) (OF-1103).

Un QIF no trae moneda (se usa la de la cuenta), ni identificador de movimiento, y sus fechas son
ambiguas (``03/04/2026``: ¿3 de abril o 4 de marzo?). Aquí **no se adivina**: se mira todo el
archivo y, si algún día mayor de 12 decide el orden, se usa; si todas las fechas valen en los dos
órdenes, se rechaza el archivo y se pide un OFX.
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
    DecimalSeparator,
    ImportFormatError,
    decode_text,
    to_decimal,
)

_MAX_DESCRIPTION = 500
_SEPARATORS = r"[/.\-]"
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_PARTS = re.compile(
    rf"^(\d{{1,2}}){_SEPARATORS}\s*(\d{{1,2}}){_SEPARATORS}\s*(?:'?\s*)?(\d{{2}}|\d{{4}})$"
)


def looks_like_qif(text: str) -> bool:
    for line in text.splitlines():
        if line.strip():
            return line.strip().lower().startswith(("!type:", "!account", "!option:"))
    return False


def _records(text: str) -> list[tuple[int, dict[str, str]]]:
    records: list[tuple[int, dict[str, str]]] = []
    current: dict[str, str] = {}
    start = 1
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if not line or line.startswith("!"):
            continue
        if line == "^":
            if current:
                records.append((start, current))
            current, start = {}, number + 1
            continue
        if not current:
            start = number
        current.setdefault(line[0], line[1:].strip())
    if current:
        records.append((start, current))
    return records


def _year(text: str) -> int:
    value = int(text)
    return value if len(text) == 4 else 2000 + value if value < 70 else 1900 + value


def _day_first(dates: list[str]) -> bool:
    """Si las fechas van día/mes (True) o mes/día (False); ``ImportFormatError`` si no se sabe."""
    first_over_12 = second_over_12 = False
    for d in dates:
        if _ISO.match(d):
            continue
        m = _PARTS.match(d.strip())
        if m is None:
            continue
        first_over_12 |= int(m.group(1)) > 12
        second_over_12 |= int(m.group(2)) > 12
    if first_over_12 and second_over_12:
        raise ImportFormatError("Las fechas del QIF mezclan día/mes y mes/día")
    if first_over_12:
        return True
    if second_over_12:
        return False
    if all(_ISO.match(d) for d in dates):
        return True
    raise ImportFormatError(
        "Las fechas del QIF son ambiguas (día/mes o mes/día): exporta el extracto en OFX"
    )


def _date(value: str, day_first: bool) -> datetime:
    iso = _ISO.match(value)
    if iso:
        return datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))  # noqa: DTZ001
    m = _PARTS.match(value.strip())
    if m is None:
        raise ValueError("fecha no válida")
    a, b, year = int(m.group(1)), int(m.group(2)), _year(m.group(3))
    day, month = (a, b) if day_first else (b, a)
    return datetime(year, month, day)  # noqa: DTZ001 - fecha local del banco


def _separator(raw: str) -> DecimalSeparator | None:
    """El separador decimal si el propio número lo deja claro («12.30» o «12,30»)."""
    if re.search(r"\.\d{1,2}$", raw):
        return "."
    if re.search(r",\d{1,2}$", raw):
        return ","
    return None


def parse_qif(content: bytes, account_key: str, rules: ClassificationRules) -> ParseResult:
    text = decode_text(content)
    if not looks_like_qif(text):
        raise ImportFormatError("No parece un archivo QIF")
    records = _records(text)
    if len(records) > MAX_ROWS:
        raise ImportFormatError(f"El archivo tiene demasiados movimientos (máximo {MAX_ROWS})")
    day_first = _day_first([f["D"] for _, f in records if "D" in f])

    result = ParseResult()
    seen: dict[str, int] = {}
    dated: list[tuple[datetime, int, ImportedRow]] = []
    for line, f in records:
        payee, memo = f.get("P", ""), f.get("M", "")
        description = (
            f"{payee} {memo}"
            if payee and memo and memo.casefold() != payee.casefold()
            else payee or memo
        )[:_MAX_DESCRIPTION]
        try:
            booked_at = _date(f.get("D", ""), day_first)
        except ValueError:
            result.skipped.append(SkippedRow(line, "fila no válida: fecha no válida", description))
            continue
        raw = f.get("T") or f.get("U") or ""
        if not raw:
            result.skipped.append(SkippedRow(line, MISSING_AMOUNT, description))
            continue
        try:
            amount = Money.of(to_decimal(raw, decimal_sep=_separator(raw)), rules.currency)
        except ValueError:
            result.skipped.append(SkippedRow(line, INVALID_AMOUNT, description))
            continue
        if amount.is_zero:
            result.skipped.append(SkippedRow(line, ZERO_AMOUNT, description))
            continue
        base = f"{booked_at.isoformat()}|{amount.amount}|{description}"
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
                    bank_type=f.get("N", "")[:40],
                    suggested_kind=kind,
                    fingerprint=fingerprint(
                        account_key, booked_at, amount, description, occurrence
                    ),
                    member=member,
                    line=line,
                ),
            )
        )
    dated.sort(key=lambda d: (d[0], d[1]))
    result.rows = [row for _, _, row in dated]
    return result
