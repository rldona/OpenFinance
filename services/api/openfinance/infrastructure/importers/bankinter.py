"""Lector del extracto de movimientos de Bankinter en Excel (.xlsx).

Estructura de la hoja «Movimientos»:

1. Un preámbulo con el número de cuenta (que no se lee) y, si los hay, los movimientos
   pendientes bajo su propia cabecera ``Fecha, Descripción, Importe, Divisa``. Se descartan:
   se importarán cuando se contabilicen.
2. Los filtros aplicados en la web (``Concepto``, ``Fecha``, ``Tipo de movimiento``…).
3. La cabecera ``Fecha contable, Fecha valor, Descripción, Importe, Saldo, Divisa`` y los
   movimientos, del más reciente al más antiguo. Las fechas son texto ``dd/mm/aaaa``.

Bankinter no da hora: dos movimientos iguales el mismo día se distinguen por el saldo tras
cada uno, que forma parte de la huella.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from openfinance.domain.imports import (
    ClassificationRules,
    ImportedRow,
    ParseResult,
    SkippedRow,
    check_running_balance,
    fingerprint,
    suggest_kind,
)
from openfinance.domain.shared import Money
from openfinance.domain.shared.text import normalize_text
from openfinance.infrastructure.importers import xlsx
from openfinance.infrastructure.importers.common import (
    INVALID_AMOUNT,
    MISSING_AMOUNT,
    ZERO_AMOUNT,
    Cell,
    ImportFormatError,
    Rows,
    cell_text,
    find_header_row,
    to_decimal,
)

_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "booked": ("fecha contable",),
    "value": ("fecha valor",),
    "description": ("descripcion", "concepto"),
    "amount": ("importe",),
    "balance": ("saldo",),
    "currency": ("divisa", "moneda"),
}
_REQUIRED = ("booked", "description", "amount", "currency")
_PENDING_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "date": ("fecha",),
    "description": ("descripcion", "concepto"),
    "amount": ("importe",),
}
_MAX_HEADER_SCAN = 1000
"""Los pendientes van antes de la cabecera: puede haber bastantes."""
_PENDING = "pendiente: se importará cuando se contabilice"
_MAX_DESCRIPTION = 500


_DECIMAL_SEP = None
"""Los importes del Excel son números. Si alguno llega como texto, solo se acepta lo que no
tiene dos lecturas: el formato del texto no se ha visto en un extracto real (bancos.md)."""


def _date(value: Cell) -> datetime:
    if isinstance(value, datetime):
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        return datetime.strptime(cell_text(value), "%d/%m/%Y")  # noqa: DTZ007 - fecha local
    except ValueError as exc:
        raise ValueError("fecha no válida") from exc


def _is_date(value: Cell) -> bool:
    try:
        _date(value)
    except ValueError:
        return False
    return True


def _pending_rows(preamble: Rows) -> list[SkippedRow]:
    found = find_header_row(preamble, _PENDING_COLUMNS, tuple(_PENDING_COLUMNS))
    if found is None:
        return []
    position, col = found
    skipped = []
    for line, row in preamble[position + 1 :]:
        if not row or not _is_date(row[col["date"]] if col["date"] < len(row) else None):
            continue
        index = col["description"]
        description = cell_text(row[index]) if index < len(row) else ""
        skipped.append(SkippedRow(line, _PENDING, description[:_MAX_DESCRIPTION]))
    return skipped


def parse_bankinter(content: bytes, account_key: str, rules: ClassificationRules) -> ParseResult:
    rows = xlsx.read_rows(content)
    found = find_header_row(rows, _COLUMNS, _REQUIRED, max_scan=_MAX_HEADER_SCAN)
    if found is None:
        raise ImportFormatError(
            "No parece un extracto de Bankinter: falta la cabecera de movimientos "
            "(Fecha contable, Descripción, Importe, Divisa)"
        )
    position, col = found

    def cell(row: list[Cell], key: str) -> Cell:
        idx = col.get(key)
        return row[idx] if idx is not None and idx < len(row) else None

    result = ParseResult(skipped=_pending_rows(rows[:position]))
    parsed: list[tuple[int, datetime, datetime, str, Money, Money | None]] = []
    for line, row in rows[position + 1 :]:
        if not any(cell_text(c) for c in row):
            continue
        description = cell_text(cell(row, "description"))[:_MAX_DESCRIPTION]
        if not cell_text(cell(row, "amount")):
            result.skipped.append(SkippedRow(line, MISSING_AMOUNT, description))
            continue
        try:
            booked_at = _date(cell(row, "booked"))
            raw_value = cell(row, "value")
            value_date = _date(raw_value) if cell_text(raw_value) else booked_at
            currency = cell_text(cell(row, "currency"))
            amount = Money.of(to_decimal(cell(row, "amount"), decimal_sep=_DECIMAL_SEP), currency)
            raw_balance = cell(row, "balance")
            balance = (
                Money.of(to_decimal(raw_balance, decimal_sep=_DECIMAL_SEP), currency)
                if cell_text(raw_balance)
                else None
            )
        except ValueError as exc:
            result.skipped.append(SkippedRow(line, f"fila no válida: {exc}", description))
            continue
        except ArithmeticError:
            result.skipped.append(SkippedRow(line, INVALID_AMOUNT, description))
            continue
        if amount.is_zero:
            result.skipped.append(SkippedRow(line, ZERO_AMOUNT, description))
            continue
        parsed.append((line, booked_at, value_date, description, amount, balance))

    # El banco lista del más reciente al más antiguo; el saldo se aplica al revés.
    parsed.reverse()
    seen: dict[tuple[str, str, str, str], int] = {}
    for line, booked_at, value_date, description, amount, balance in parsed:
        discriminator = str(balance.amount) if balance is not None else ""
        key = (booked_at.isoformat(), str(amount), normalize_text(description), discriminator)
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        kind, member = suggest_kind(description, is_inflow=amount.amount > 0, rules=rules)
        result.rows.append(
            ImportedRow(
                booked_at=booked_at,
                value_date=value_date.date(),
                description=description,
                amount=amount,
                bank_type="",
                suggested_kind=kind,
                member=member,
                fingerprint=fingerprint(
                    account_key,
                    booked_at,
                    amount,
                    description,
                    occurrence,
                    discriminator=discriminator,
                ),
                balance_after=balance,
                line=line,
            )
        )
    result.balance_mismatches = check_running_balance(result.rows)
    return result
