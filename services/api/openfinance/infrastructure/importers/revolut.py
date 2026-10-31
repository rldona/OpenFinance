"""Lector del extracto CSV de Revolut (cuenta personal o conjunta).

Formato esperado (exportación «Excel/CSV» del extracto):
``Type, Product, Started Date, Completed Date, Description, Amount, Fee, Currency, State, Balance``
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Collection, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

from openfinance.domain.imports import (
    ClassificationRules,
    ImportedRow,
    ParseResult,
    SkippedRow,
    check_running_balance,
    fingerprint,
    suggest_kind,
)
from openfinance.domain.imports.model import normalize_text
from openfinance.domain.shared import Money


class ImportFormatError(ValueError):
    """El archivo no tiene el formato esperado."""


# Cabeceras admitidas. Las españolas son una suposición hasta tener una muestra real.
_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "type": ("type", "tipo"),
    "product": ("product", "producto"),
    "started": ("started date", "fecha de inicio"),
    "completed": ("completed date", "fecha de finalizacion", "fecha de finalización"),
    "description": ("description", "descripcion", "descripción"),
    "amount": ("amount", "importe"),
    "fee": ("fee", "comision", "comisión"),
    "currency": ("currency", "divisa", "moneda"),
    "state": ("state", "estado"),
    "balance": ("balance", "saldo"),
}
_REQUIRED = ("started", "description", "amount", "currency", "state")
_MAX_DESCRIPTION = 500
_MAX_BANK_TYPE = 40
_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
_REFUND_TYPES = frozenset({"REFUND", "CARD_REFUND"})
_COMPLETED = frozenset({"COMPLETED", "COMPLETADO", "COMPLETADA"})
_SKIP_REASONS = {
    "PENDING": "pendiente: se importará cuando se complete",
    "REVERTED": "revertida por el banco",
    "DECLINED": "rechazada",
    "FAILED": "fallida",
}


@dataclass(frozen=True, slots=True)
class RevolutProfile:
    account_key: str
    """Identificador estable de la cuenta en OpenFinance; forma parte de la huella."""
    rules: ClassificationRules = field(default_factory=ClassificationRules)
    products: Collection[str] = ("CURRENT", "ACTUAL")
    """Productos que pertenecen a la cuenta. Las filas de huchas (``SAVINGS``) se omiten:
    el traspaso ya aparece en la cuenta principal."""


def _header_map(header: list[str]) -> dict[str, int]:
    normalized = [normalize_text(h).lower() for h in header]
    found: dict[str, int] = {}
    for key, aliases in _COLUMNS.items():
        for alias in aliases:
            target = normalize_text(alias).lower()
            if target in normalized:
                found[key] = normalized.index(target)
                break
    missing = [k for k in _REQUIRED if k not in found]
    if missing:
        raise ImportFormatError(
            f"No parece un extracto de Revolut: faltan las columnas {', '.join(missing)}"
        )
    return found


def _decimal(raw: str) -> Decimal:
    text = raw.strip().replace(" ", "")
    if not text:
        return Decimal(0)
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"importe no válido: {raw!r}") from exc


def _datetime(raw: str) -> datetime:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt)  # noqa: DTZ007 - hora local del extracto
        except ValueError:
            continue
    raise ValueError(f"fecha no válida: {raw!r}")


def parse_revolut_csv(content: bytes | str, profile: RevolutProfile) -> ParseResult:
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content.lstrip("\ufeff")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ImportFormatError("El archivo está vacío") from exc
    except csv.Error as exc:
        raise ImportFormatError(f"CSV mal formado: {exc}") from exc
    col = _header_map(header)
    products = {p.upper() for p in profile.products}

    def cell(row: list[str], key: str) -> str:
        idx = col.get(key)
        return row[idx].strip() if idx is not None and idx < len(row) else ""

    result = ParseResult()

    try:
        _read_rows(reader, cell, products, profile, result)
    except csv.Error as exc:
        raise ImportFormatError(f"CSV mal formado: {exc}") from exc
    result.balance_mismatches = check_running_balance(result.rows)
    return result


def _read_rows(
    reader: Iterator[list[str]],
    cell: Callable[[list[str], str], str],
    products: set[str],
    profile: RevolutProfile,
    result: ParseResult,
) -> None:
    seen: dict[tuple[str, str, str], int] = {}
    for line, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        description = cell(row, "description")[:_MAX_DESCRIPTION]
        state = cell(row, "state").upper()
        if state not in _COMPLETED:
            reason = _SKIP_REASONS.get(state, f"estado desconocido: {state or 'vacío'}")
            result.skipped.append(SkippedRow(line, reason, description))
            continue
        product = cell(row, "product").upper()
        if product and product not in products:
            reason = f"producto {product.lower()} (hucha o ahorro)"
            result.skipped.append(SkippedRow(line, reason, description))
            continue
        try:
            booked_at = _datetime(cell(row, "started"))
            completed = cell(row, "completed")
            value_date = _datetime(completed).date() if completed else booked_at.date()
            currency = cell(row, "currency")
            amount = Money.of(_decimal(cell(row, "amount")) - _decimal(cell(row, "fee")), currency)
            balance_raw = cell(row, "balance")
            balance = Money.of(_decimal(balance_raw), currency) if balance_raw else None
        except ValueError as exc:
            result.skipped.append(SkippedRow(line, f"fila no válida: {exc}", description))
            continue

        bank_type = cell(row, "type").upper()[:_MAX_BANK_TYPE]
        kind, member = suggest_kind(
            description,
            is_inflow=amount.amount > 0,
            rules=profile.rules,
            is_refund=bank_type in _REFUND_TYPES,
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
