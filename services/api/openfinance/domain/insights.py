"""Agregados para los gráficos del hogar (OF-301). Funciones puras sobre movimientos."""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from openfinance.domain.categories import CategoryId
from openfinance.domain.ledger import Summary, Transaction, TransactionKind
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import UserId


@dataclass(frozen=True, order=True, slots=True)
class Month:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12 or not 1 <= self.year <= 9998:
            raise ValueError("Mes no válido")

    @classmethod
    def parse(cls, text: str) -> Month:
        year, month = text.split("-")
        return cls(int(year), int(month))

    @classmethod
    def of(cls, value: date | datetime) -> Month:
        return cls(value.year, value.month)

    def shift(self, delta: int) -> Month:
        index = self.year * 12 + self.month - 1 + delta
        return Month(index // 12, index % 12 + 1)

    @property
    def days(self) -> int:
        return calendar.monthrange(self.year, self.month)[1]

    @property
    def start(self) -> datetime:
        return datetime(self.year, self.month, 1)  # noqa: DTZ001 - hora local del extracto

    @property
    def end(self) -> datetime:
        return datetime(self.year, self.month, self.days, 23, 59, 59, 999999)  # noqa: DTZ001

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def by_month(transactions: Iterable[Transaction]) -> dict[Month, list[Transaction]]:
    out: dict[Month, list[Transaction]] = defaultdict(list)
    for t in transactions:
        out[Month.of(t.booked_at)].append(t)
    return out


def spending_by_category(
    transactions: Iterable[Transaction], currency: Currency
) -> dict[CategoryId | None, Money]:
    """Gasto neto por categoría (gastos menos devoluciones). ``None`` = sin categoría."""
    out: dict[CategoryId | None, Money] = {}
    for t in transactions:
        if t.kind is TransactionKind.EXPENSE:
            out[t.category_id] = out.get(t.category_id, Money.zero(currency)) - t.amount
    return out


def contributions_by_member(
    transactions: Iterable[Transaction], currency: Currency
) -> dict[UserId, Money]:
    out: dict[UserId, Money] = {}
    for t in transactions:
        if t.kind is TransactionKind.CONTRIBUTION and t.member_id and not t.amount.is_negative:
            out[t.member_id] = out.get(t.member_id, Money.zero(currency)) + t.amount
    return out


def daily_cumulative_spent(
    transactions: Iterable[Transaction], month: Month, currency: Currency
) -> list[Money]:
    """Gasto neto acumulado al final de cada día del mes."""
    per_day = [Money.zero(currency) for _ in range(month.days)]
    for t in transactions:
        if t.kind is TransactionKind.EXPENSE and Month.of(t.booked_at) == month:
            per_day[t.booked_at.day - 1] = per_day[t.booked_at.day - 1] - t.amount
    out: list[Money] = []
    total = Money.zero(currency)
    for value in per_day:
        total = total + value
        out.append(total)
    return out


@dataclass(frozen=True, slots=True)
class MerchantTotal:
    merchant: str
    spent: Money
    count: int


def top_merchants(
    transactions: Iterable[Transaction], currency: Currency, limit: int = 5
) -> list[MerchantTotal]:
    totals: dict[str, Money] = {}
    counts: dict[str, int] = defaultdict(int)
    for t in transactions:
        if t.kind is TransactionKind.EXPENSE:
            key = t.merchant or "—"
            totals[key] = totals.get(key, Money.zero(currency)) - t.amount
            counts[key] += 1
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1].amount, kv[0]))
    return [MerchantTotal(m, v, counts[m]) for m, v in ranked[:limit] if v.amount > 0]


def average(values: Sequence[Money], currency: Currency) -> Money | None:
    """Media exacta redondeada a céntimos; ``None`` si no hay valores."""
    if not values:
        return None
    total = Money.zero(currency)
    for v in values:
        total = total + v
    return Money.of(total.amount / len(values), currency)


def saving_rate(summary: Summary) -> int | None:
    """Porcentaje de lo que entra que se ahorra, redondeado; ``None`` si no entra nada."""
    if summary.inflow.amount <= 0:
        return None
    return int((summary.saved.amount * 100 / summary.inflow.amount).to_integral_value())
