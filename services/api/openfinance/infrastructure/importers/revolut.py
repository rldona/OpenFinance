"""Lector del extracto de Revolut (cuenta personal o conjunta), en CSV o en Excel.

Formato CSV (exportación en inglés):
``Type, Product, Started Date, Completed Date, Description, Amount, Fee, Currency, State, Balance``

Formato XLSX (exportación en español, hoja única): ``Tipo, Producto, Fecha de inicio,
Fecha de finalización, Descripción, Importe, Comisión, Divisa, State, Saldo``. Algunas
cabeceras llegan con la codificación rota (``DescripciÃ³n``) y se reparan. Las fechas son
fechas de Excel y los importes, números.

Las filas se devuelven en el orden del archivo, que es el de finalización: en ese orden
cuadra el saldo.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
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
from openfinance.infrastructure.importers import common, xlsx
from openfinance.infrastructure.importers.common import (
    INVALID_AMOUNT,
    Cell,
    ImportFormatError,
    Rows,
    cell_text,
    find_header_row,
    repair_text_cells,
    to_decimal,
)

__all__ = [
    "ImportFormatError",
    "RevolutProfile",
    "parse_revolut",
    "parse_revolut_csv",
    "parse_revolut_xlsx",
]

_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "type": ("type", "tipo"),
    "product": ("product", "producto"),
    "started": ("started date", "fecha de inicio"),
    "completed": ("completed date", "fecha de finalizacion"),
    "description": ("description", "descripcion"),
    "amount": ("amount", "importe"),
    "fee": ("fee", "comision"),
    "currency": ("currency", "divisa", "moneda"),
    "state": ("state", "estado"),
    "balance": ("balance", "saldo"),
}
_REQUIRED = ("started", "description", "amount", "currency", "state")
_MAX_DESCRIPTION = 500
_MAX_BANK_TYPE = 40
_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
_REFUND_TYPES = frozenset({"REFUND", "CARD_REFUND"})
_CARD_PAYMENT_TYPES = frozenset({"CARD_PAYMENT", "PAGO CON TARJETA"})
_COMPLETED = frozenset({"COMPLETED", "COMPLETADO", "COMPLETADA"})
_PENDING = "pendiente: se importará cuando se complete"
_REVERTED = "revertida por el banco"
_DECLINED = "rechazada"
_FAILED = "fallida"
_SKIP_REASONS = {
    "PENDING": _PENDING,
    "PENDIENTE": _PENDING,
    "REVERTED": _REVERTED,
    "REVERTIDO": _REVERTED,
    "REVERTIDA": _REVERTED,
    "DECLINED": _DECLINED,
    "RECHAZADO": _DECLINED,
    "RECHAZADA": _DECLINED,
    "FAILED": _FAILED,
    "FALLIDO": _FAILED,
    "FALLIDA": _FAILED,
}


@dataclass(frozen=True, slots=True)
class RevolutProfile:
    account_key: str
    """Identificador estable de la cuenta en OpenFinance; forma parte de la huella."""
    rules: ClassificationRules = field(default_factory=ClassificationRules)
    products: Collection[str] = ("CURRENT", "ACTUAL")
    """Productos que pertenecen a la cuenta. Las filas de huchas (``SAVINGS``) se omiten:
    el traspaso ya aparece en la cuenta principal."""


def _missing_columns(rows: Rows) -> ImportFormatError:
    header = rows[0][1] if rows else []
    found = find_header_row([(1, header)], _COLUMNS, ())
    present = found[1] if found else {}
    missing = [k for k in _REQUIRED if k not in present]
    return ImportFormatError(
        f"No parece un extracto de Revolut: faltan las columnas {', '.join(missing)}"
    )


def _datetime(value: Cell) -> datetime:
    if isinstance(value, datetime):
        return value
    raw = cell_text(value)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)  # noqa: DTZ007 - hora local del extracto
        except ValueError:
            continue
    raise ValueError(f"fecha no válida: {raw!r}")


def parse_revolut(content: bytes, profile: RevolutProfile) -> ParseResult:
    """Detecta si el extracto es Excel o CSV y lo lee."""
    if xlsx.is_xlsx(content) or xlsx.is_legacy_xls(content):
        return parse_revolut_xlsx(content, profile)
    return parse_revolut_csv(content, profile)


def _csv_rows(text: str) -> Iterator[tuple[int, list[Cell]]]:
    """Filas con contenido del CSV, de una en una y con límites de filas y columnas.

    Las filas vacías se saltan sin acumularlas.
    """
    count = 0
    try:
        for line, row in enumerate(csv.reader(io.StringIO(text)), start=1):
            if not any(c.strip() for c in row):
                continue
            count += 1
            if count > common.MAX_ROWS:
                raise ImportFormatError(f"El archivo supera las {common.MAX_ROWS} filas")
            yield line, list[Cell](row[: common.MAX_COLS])
    except csv.Error as exc:
        raise ImportFormatError(f"CSV mal formado: {exc}") from exc


def parse_revolut_csv(content: bytes | str, profile: RevolutProfile) -> ParseResult:
    """El CSV se lee tal cual: sin reparar la codificación, para no cambiar sus huellas."""
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ImportFormatError("El archivo no es un CSV en UTF-8") from exc
    else:
        text = content.lstrip("\ufeff")
    rows = _csv_rows(text)
    first = next(rows, None)
    if first is None:
        raise ImportFormatError("El archivo está vacío")
    found = find_header_row([first], _COLUMNS, _REQUIRED)
    if found is None:
        raise _missing_columns([first])
    return _parse_rows(rows, found[1], profile)


def parse_revolut_xlsx(content: bytes, profile: RevolutProfile) -> ParseResult:
    """La exportación en Excel trae texto UTF-8 mal decodificado: se repara antes de leer."""
    rows = repair_text_cells(xlsx.read_rows(content))
    found = find_header_row(rows, _COLUMNS, _REQUIRED)
    if found is None:
        raise _missing_columns(rows)
    position, col = found
    return _parse_rows(rows[position + 1 :], col, profile)


def _parse_rows(
    rows: Iterable[tuple[int, list[Cell]]], col: dict[str, int], profile: RevolutProfile
) -> ParseResult:
    products = {p.upper() for p in profile.products}

    def cell(row: list[Cell], key: str) -> Cell:
        idx = col.get(key)
        return row[idx] if idx is not None and idx < len(row) else None

    def text(row: list[Cell], key: str) -> str:
        return cell_text(cell(row, key))

    result = ParseResult()
    seen: dict[tuple[str, str, str], int] = {}
    for line, row in rows:
        if not any(cell_text(c) for c in row):
            continue
        description = text(row, "description")[:_MAX_DESCRIPTION]
        state = normalize_text(text(row, "state"))
        if state not in _COMPLETED:
            reason = _SKIP_REASONS.get(state, f"estado desconocido: {state or 'vacío'}")
            result.skipped.append(SkippedRow(line, reason, description))
            continue
        product = normalize_text(text(row, "product"))
        if product and product not in products:
            reason = f"producto {product.lower()} (hucha o ahorro)"
            result.skipped.append(SkippedRow(line, reason, description))
            continue
        try:
            booked_at = _datetime(cell(row, "started"))
            completed = cell(row, "completed")
            value_date = _datetime(completed).date() if cell_text(completed) else booked_at.date()
            currency = text(row, "currency")
            amount = Money.of(
                to_decimal(cell(row, "amount")) - to_decimal(cell(row, "fee")), currency
            )
            balance_raw = cell(row, "balance")
            balance = (
                Money.of(to_decimal(balance_raw), currency) if cell_text(balance_raw) else None
            )
        except ValueError as exc:
            result.skipped.append(SkippedRow(line, f"fila no válida: {exc}", description))
            continue
        except ArithmeticError:
            result.skipped.append(SkippedRow(line, INVALID_AMOUNT, description))
            continue

        bank_type = text(row, "type").upper()[:_MAX_BANK_TYPE]
        normalized_type = normalize_text(bank_type)
        is_refund = normalized_type in _REFUND_TYPES or (
            normalized_type in _CARD_PAYMENT_TYPES and amount.amount > 0
        )
        kind, member = suggest_kind(
            description, is_inflow=amount.amount > 0, rules=profile.rules, is_refund=is_refund
        )
        key = (booked_at.isoformat(), str(amount), normalize_text(description))
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1

        result.rows.append(
            ImportedRow(
                booked_at=booked_at,
                value_date=value_date,
                description=description,
                amount=amount,
                bank_type=bank_type,
                suggested_kind=kind,
                member=member,
                fingerprint=fingerprint(
                    profile.account_key, booked_at, amount, description, occurrence
                ),
                balance_after=balance,
                line=line,
            )
        )
    result.balance_mismatches = check_running_balance(result.rows)
    return result
