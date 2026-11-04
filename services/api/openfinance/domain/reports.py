"""Informes a medida: una definición cerrada que se ejecuta con los permisos de quien la ejecuta
(ADR-0025, OF-1503).

No hay expresiones ni lenguaje de consulta: solo campos cerrados y validados. Una definición
no guarda datos; el mismo informe da resultados distintos a cada persona porque cada una ve
cuentas distintas.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from uuid import UUID

from openfinance.domain.insights import Month
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import TransactionId, UserId, WorkspaceId
from openfinance.domain.tags import tag_key

MAX_MONTHS = 36
MAX_FILTER = 50
MAX_ROWS = 100
MAX_SAVED_PER_PERSON = 30
MAX_NAME = 80


class ReportError(ValueError):
    pass


class Measure(StrEnum):
    SPENT = "spent"
    """Gasto neto de devoluciones."""
    INCOME = "income"
    SAVED = "saved"
    """Lo movido al ahorro, neto de lo que se saca."""
    NET = "net"
    """Ingresos menos gasto."""


class GroupBy(StrEnum):
    CATEGORY = "category"
    MERCHANT = "merchant"
    ACCOUNT = "account"
    MONTH = "month"


@dataclass(frozen=True, slots=True)
class ReportDefinition:
    from_month: Month
    to_month: Month
    measure: Measure
    group_by: GroupBy
    account_ids: tuple[UUID, ...] = ()
    """Vacío = todas las cuentas que ve quien lo ejecuta."""
    category_ids: tuple[UUID, ...] = ()
    uncategorized: bool = False
    """Incluir también los gastos sin categoría cuando se filtra por categorías."""
    tags: tuple[str, ...] = ()
    """Movimientos con alguna de estas etiquetas."""
    min_amount: Decimal | None = None
    """Ignora los movimientos de menos de este importe (en valor absoluto)."""

    def __post_init__(self) -> None:
        if self.to_month < self.from_month:
            raise ReportError("El periodo termina antes de empezar")
        span = (self.to_month.year - self.from_month.year) * 12 + (
            self.to_month.month - self.from_month.month
        )
        if span + 1 > MAX_MONTHS:
            raise ReportError(f"El periodo no puede pasar de {MAX_MONTHS} meses")
        if len(self.account_ids) > MAX_FILTER or len(self.category_ids) > MAX_FILTER:
            raise ReportError(f"Un filtro admite como máximo {MAX_FILTER} elementos")
        if len(self.tags) > MAX_FILTER:
            raise ReportError(f"Un filtro admite como máximo {MAX_FILTER} elementos")
        if self.min_amount is not None and (not self.min_amount.is_finite() or self.min_amount < 0):
            raise ReportError("El importe mínimo no es válido")

    @property
    def filters_categories(self) -> bool:
        return bool(self.category_ids) or self.uncategorized


def make_definition(
    from_month: str,
    to_month: str,
    measure: str,
    group_by: str,
    *,
    account_ids: Iterable[UUID] = (),
    category_ids: Iterable[UUID] = (),
    uncategorized: bool = False,
    tags: Iterable[str] = (),
    min_amount: str | None = None,
) -> ReportDefinition:
    """Construye y valida una definición a partir de datos de fuera (API o base de datos)."""
    try:
        cleaned = _clean_filter_tags(tags)
        minimum = Decimal(min_amount) if min_amount not in (None, "") else None
        return ReportDefinition(
            Month.parse(from_month),
            Month.parse(to_month),
            Measure(measure),
            GroupBy(group_by),
            tuple(dict.fromkeys(account_ids)),
            tuple(dict.fromkeys(category_ids)),
            uncategorized,
            cleaned,
            minimum,
        )
    except (ValueError, InvalidOperation) as exc:
        raise ReportError(str(exc)) from exc


def _clean_filter_tags(tags: Iterable[str]) -> tuple[str, ...]:
    """Etiquetas limpias para filtrar. No se limita a 10 como un movimiento: es un filtro."""
    seen: dict[str, str] = {}
    for raw in tags:
        tag = " ".join(raw.split()).lstrip("#").strip()
        if not tag or "|" in tag or not tag.isprintable() or len(tag) > 40:
            raise ReportError("Etiqueta no válida")
        seen.setdefault(tag_key(tag), tag)
    return tuple(seen[k] for k in sorted(seen))


def to_dict(d: ReportDefinition) -> dict[str, Any]:
    return {
        "from_month": str(d.from_month),
        "to_month": str(d.to_month),
        "measure": d.measure.value,
        "group_by": d.group_by.value,
        "account_ids": [str(i) for i in d.account_ids],
        "category_ids": [str(i) for i in d.category_ids],
        "uncategorized": d.uncategorized,
        "tags": list(d.tags),
        "min_amount": str(d.min_amount) if d.min_amount is not None else None,
    }


def from_dict(data: Mapping[str, Any]) -> ReportDefinition:
    return make_definition(
        str(data["from_month"]),
        str(data["to_month"]),
        str(data["measure"]),
        str(data["group_by"]),
        account_ids=[UUID(str(i)) for i in data.get("account_ids", [])],
        category_ids=[UUID(str(i)) for i in data.get("category_ids", [])],
        uncategorized=bool(data.get("uncategorized", False)),
        tags=[str(t) for t in data.get("tags", [])],
        min_amount=data.get("min_amount"),
    )


@dataclass(frozen=True, slots=True)
class SavedReport:
    id: UUID
    household_id: WorkspaceId
    owner_id: UserId
    name: str
    definition: ReportDefinition
    shared: bool
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > MAX_NAME or not self.name.isprintable():
            raise ReportError(f"El nombre va de 1 a {MAX_NAME} caracteres")


def clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > MAX_NAME or not cleaned.isprintable():
        raise ReportError(f"El nombre va de 1 a {MAX_NAME} caracteres")
    return cleaned


@dataclass(frozen=True, slots=True)
class ReportRow:
    key: str | None
    """Categoría, comercio, cuenta o mes; ``None`` = sin categoría."""
    amount: Money
    count: int


def _contribution(measure: Measure, t: Transaction, zero: Money) -> Money | None:
    """Lo que un movimiento aporta a la medida, o ``None`` si no cuenta."""
    kind = t.kind
    if measure is Measure.SPENT:
        return -t.amount if kind is TransactionKind.EXPENSE else None
    if measure is Measure.INCOME:
        return t.amount if kind is TransactionKind.INCOME else None
    if measure is Measure.SAVED:
        return -t.amount if kind is TransactionKind.SAVINGS_TRANSFER else None
    if kind in (TransactionKind.INCOME, TransactionKind.EXPENSE):
        return t.amount
    return None


def _group_key(group_by: GroupBy, t: Transaction) -> str | None:
    match group_by:
        case GroupBy.CATEGORY:
            return str(t.category_id) if t.category_id else None
        case GroupBy.MERCHANT:
            return t.merchant or None
        case GroupBy.ACCOUNT:
            return str(t.account_id)
        case GroupBy.MONTH:
            return str(Month.of(t.booked_at))


def matches(
    d: ReportDefinition, t: Transaction, tags: Mapping[TransactionId, tuple[str, ...]]
) -> bool:
    if t.voided:
        return False
    month = Month.of(t.booked_at)
    if not d.from_month <= month <= d.to_month:
        return False
    if d.account_ids and t.account_id not in d.account_ids:
        return False
    if d.filters_categories:
        in_category = t.category_id is not None and t.category_id in d.category_ids
        if not in_category and not (d.uncategorized and t.category_id is None):
            return False
    if d.min_amount is not None and abs(t.amount.amount) < d.min_amount:
        return False
    if d.tags:
        wanted = {tag_key(x) for x in d.tags}
        if not wanted & {tag_key(x) for x in tags.get(t.id, ())}:
            return False
    return True


@dataclass(frozen=True, slots=True)
class ReportResult:
    rows: list[ReportRow]
    total: Money
    count: int
    hidden_rows: int
    """Filas que no caben en la lista (se quedan las ``MAX_ROWS`` de más peso)."""


def aggregate(
    d: ReportDefinition,
    transactions: Iterable[Transaction],
    currency: Currency,
    tags: Mapping[TransactionId, tuple[str, ...]],
) -> ReportResult:
    zero = Money.zero(currency)
    totals: dict[str | None, Money] = defaultdict(lambda: zero)
    counts: dict[str | None, int] = defaultdict(int)
    for t in transactions:
        if not matches(d, t, tags):
            continue
        part = _contribution(d.measure, t, zero)
        if part is None:
            continue
        key = _group_key(d.group_by, t)
        totals[key] = totals[key] + part
        counts[key] += 1
    rows = [ReportRow(k, v, counts[k]) for k, v in totals.items()]
    if d.group_by is GroupBy.MONTH:
        rows.sort(key=lambda r: r.key or "")
    else:
        rows.sort(key=lambda r: (-abs(r.amount.amount), r.key or ""))
    total = zero
    for r in rows:
        total = total + r.amount
    hidden = max(0, len(rows) - MAX_ROWS)
    return ReportResult(rows[:MAX_ROWS], total, sum(counts.values()), hidden)
