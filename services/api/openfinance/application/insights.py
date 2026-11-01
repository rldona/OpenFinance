"""Datos de los gráficos del hogar (OF-301) y de la vista «mi gasto» (OF-108).

Los totales del hogar salen solo de la cuenta conjunta y las huchas (ADR-0013): las cuentas
personales no entran, aunque quien consulta pueda verlas. La vista «mío» usa solo las cuentas
personales de quien pregunta, nunca las de otra persona.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from openfinance.application.errors import NotFoundError
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import CategoryId
from openfinance.domain.insights import (
    MerchantTotal,
    Month,
    average,
    by_month,
    contributions_by_member,
    contributions_out,
    daily_cumulative_spent,
    saving_rate,
    spending_by_category,
    spending_by_category_until,
    top_merchants,
)
from openfinance.domain.ledger import AccountKind, Summary, summarize
from openfinance.domain.savings import (
    PendingCharge,
    detect_recurring,
    forecast_month_end,
    is_fixed,
    pending_charges,
)
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, UserId
from openfinance.domain.workspaces import Actor

HISTORY_MONTHS = 12
MERCHANT_MONTHS = 3
MIN_CHANGE = Money.of("20", "EUR").amount
"""Por debajo de esto (gasto y referencia), un cambio no se destaca en «Este mes»."""
MAX_CHANGES = 4


class View(StrEnum):
    HOUSEHOLD = "household"
    """Cuenta conjunta y huchas: los totales del hogar."""
    MINE = "mine"
    """Las cuentas personales de quien pregunta (OF-108)."""


@dataclass(frozen=True, slots=True)
class Scope:
    currency: Currency
    accounts: list[AccountId]
    first: Month | None
    """Primer mes con movimientos en esas cuentas."""


def scope_of(uow: UnitOfWork, actor: Actor, view: View) -> Scope:
    household = uow.households.get(actor.household_id)
    if household is None:
        raise NotFoundError("Hogar no encontrado")
    accounts = uow.accounts.for_household(actor.household_id)
    if view is View.MINE:
        ids = [
            a.id for a in accounts if a.kind is AccountKind.PERSONAL and a.owner_id == actor.user_id
        ]
    else:
        ids = [a.id for a in accounts if a.kind in (AccountKind.JOINT, AccountKind.SAVINGS)]
    first = uow.transactions.first_booked_at(actor.household_id, ids)
    return Scope(household.currency, ids, Month.of(first) if first else None)


def shared_scope(uow: UnitOfWork, actor: Actor) -> Scope:
    return scope_of(uow, actor, View.HOUSEHOLD)


def has_data(scope: Scope, month: Month) -> bool:
    return scope.first is not None and month >= scope.first


@dataclass(frozen=True, slots=True)
class CategoryAmount:
    category_id: CategoryId | None
    amount: Money
    average: Money | None
    """Media de los meses completos anteriores con datos (hasta 12)."""
    reference: Money | None
    """Con qué se compara: la media, o en el mes en curso la media hasta el mismo día."""

    @property
    def change(self) -> Money | None:
        return self.amount - self.reference if self.reference is not None else None


def largest_changes(categories: list[CategoryAmount]) -> list[CategoryAmount]:
    """Las categorías que más se alejan de su referencia, sin las de importes pequeños."""
    relevant = [
        c
        for c in categories
        if c.change is not None
        and (c.amount.amount >= MIN_CHANGE or (c.reference and c.reference.amount >= MIN_CHANGE))
    ]
    relevant.sort(key=lambda c: -abs(c.change.amount) if c.change else 0)
    return relevant[:MAX_CHANGES]


@dataclass(frozen=True, slots=True)
class MonthOverview:
    month: Month
    currency: Currency
    has_data: bool
    summary: Summary
    previous_spent: Money | None
    is_partial: bool
    """Mes en curso: los datos llegan hasta ``days_elapsed``."""
    days_elapsed: int
    previous_spent_to_date: Money | None
    """Gasto del mes anterior hasta el mismo día, para comparar un mes en curso."""
    average_spent: Money | None
    """Media de gasto de los meses anteriores con datos (hasta 12)."""
    saving_rate: int | None
    contributions: dict[UserId, Money]
    contributed: Money
    """Lo aportado desde estas cuentas a la conjunta. No es gasto."""
    categories: list[CategoryAmount]
    changes: list[CategoryAmount]
    """Las categorías que más cambian frente a su referencia (OF-608)."""
    daily: list[Money]
    previous_daily: list[Money]
    forecast: Money | None
    """Gasto con el que cerraría el mes en curso (OF-802); ``None`` si hay pocos días."""
    pending: list[PendingCharge]
    """Cuotas habituales que este mes todavía no han llegado (solo el mes en curso)."""


def month_overview(
    uow: UnitOfWork, actor: Actor, month: Month, today: date, view: View = View.HOUSEHOLD
) -> MonthOverview:
    scope = scope_of(uow, actor, view)
    start = month.shift(-HISTORY_MONTHS)
    txns = uow.transactions.in_range(actor.household_id, scope.accounts, start.start, month.end)
    months = by_month(txns)
    cur = scope.currency
    now = months.get(month, [])
    prev_month = month.shift(-1)
    history = [
        m for m in (month.shift(-i) for i in range(1, HISTORY_MONTHS + 1)) if has_data(scope, m)
    ]
    summary = summarize(now, cur)
    spent_history = [summarize(months.get(m, []), cur).spent for m in history]

    is_partial = month == Month.of(today)
    days_elapsed = today.day if is_partial else month.days

    by_cat = spending_by_category(now, cur)
    hist_by_cat = [spending_by_category(months.get(m, []), cur) for m in history]
    # En el mes en curso se compara con lo gastado hasta el mismo día de los meses anteriores:
    # contra el mes entero, el día 1 todo parecería muy por debajo de su media.
    hist_to_date = (
        [
            spending_by_category_until(months.get(m, []), min(days_elapsed, m.days), cur)
            for m in history
        ]
        if is_partial
        else hist_by_cat
    )
    keys = set(by_cat) | {k for h in hist_by_cat for k in h}
    zero = Money.zero(cur)
    categories = [
        CategoryAmount(
            k,
            by_cat.get(k, zero),
            average([h.get(k, zero) for h in hist_by_cat], cur),
            average([h.get(k, zero) for h in hist_to_date], cur),
        )
        for k in keys
    ]
    categories.sort(key=lambda c: (-c.amount.amount, -(c.average.amount if c.average else 0)))
    prev_has_data = has_data(scope, prev_month)
    previous_daily = (
        daily_cumulative_spent(months.get(prev_month, []), prev_month, cur) if prev_has_data else []
    )
    pending: list[PendingCharge] = []
    forecast: Money | None = None
    if is_partial:
        recurring = detect_recurring(txns, cur, today)
        pending = pending_charges(recurring, now, today)
        merchants = {r.merchant for r in recurring}
        fixed_paid = Money.zero(cur)
        for t in now:
            if is_fixed(t, merchants):
                fixed_paid = fixed_paid - t.amount
        forecast = forecast_month_end(
            summary.spent, fixed_paid, pending, days_elapsed, month.days, cur
        )
    return MonthOverview(
        month=month,
        currency=cur,
        has_data=has_data(scope, month),
        summary=summary,
        previous_spent=previous_daily[-1] if previous_daily else None,
        is_partial=is_partial,
        days_elapsed=days_elapsed,
        previous_spent_to_date=previous_daily[min(days_elapsed, prev_month.days) - 1]
        if previous_daily
        else None,
        average_spent=average(spent_history, cur),
        saving_rate=saving_rate(summary),
        contributions=contributions_by_member(now, cur),
        contributed=contributions_out(now, cur),
        categories=categories,
        changes=largest_changes(categories),
        daily=daily_cumulative_spent(now, month, cur)[:days_elapsed],
        previous_daily=previous_daily,
        forecast=forecast,
        pending=pending,
    )


@dataclass(frozen=True, slots=True)
class MonthAmount:
    month: Month
    amount: Money
    has_data: bool


@dataclass(frozen=True, slots=True)
class CategoryDetail:
    category_id: CategoryId | None
    month: Month
    months: list[MonthAmount]
    average: Money | None
    """Media de los meses anteriores al elegido con datos."""
    merchants: list[MerchantTotal]


def category_detail(
    uow: UnitOfWork,
    actor: Actor,
    category_id: CategoryId | None,
    month: Month,
    view: View = View.HOUSEHOLD,
) -> CategoryDetail:
    if category_id is not None and uow.categories.get(actor.household_id, category_id) is None:
        raise NotFoundError("Categoría no encontrada")
    scope = scope_of(uow, actor, view)
    cur = scope.currency
    first = month.shift(-(HISTORY_MONTHS - 1))
    txns = [
        t
        for t in uow.transactions.in_range(
            actor.household_id, scope.accounts, first.start, month.end
        )
        if t.category_id == category_id
    ]
    months = by_month(txns)
    series = [
        MonthAmount(
            m,
            spending_by_category(months.get(m, []), cur).get(category_id, Money.zero(cur)),
            has_data(scope, m),
        )
        for m in (first.shift(i) for i in range(HISTORY_MONTHS))
    ]
    previous = [s.amount for s in series[:-1] if s.has_data]
    recent = [
        t for m in (month.shift(-i) for i in range(MERCHANT_MONTHS)) for t in months.get(m, [])
    ]
    return CategoryDetail(
        category_id, month, series, average(previous, cur), top_merchants(recent, cur)
    )


@dataclass(frozen=True, slots=True)
class TrendMonth:
    month: Month
    has_data: bool
    summary: Summary
    categories: dict[CategoryId | None, Money]
    is_partial: bool = False
    """Mes en curso: cuenta en los totales, no en las medias ni en el mejor o peor mes."""


@dataclass(frozen=True, slots=True)
class Trends:
    currency: Currency
    months: list[TrendMonth]
    total_saved: Money
    total_inflow: Money
    total_spent: Money
    average_spent: Money | None
    average_saved: Money | None
    saving_rate: int | None
    """% de lo que entró que se ahorró en el periodo, redondeado como en el resumen mensual."""
    best: TrendMonth | None
    worst: TrendMonth | None


def trends(
    uow: UnitOfWork, actor: Actor, month: Month, today: date, count: int = HISTORY_MONTHS
) -> Trends:
    """Evolución de ``count`` meses hasta ``month``.

    Las medias son de meses completos: si el periodo llega al mes en curso, se toman los
    ``count`` meses anteriores a él, como en «Este mes», para que las dos den la misma media.
    """
    scope = shared_scope(uow, actor)
    cur = scope.currency
    current = Month.of(today)
    first = month.shift(-(count - 1))
    last_complete = month if month < current else current.shift(-1)
    months = by_month(
        uow.transactions.in_range(
            actor.household_id,
            scope.accounts,
            min(first, last_complete.shift(-(count - 1))).start,
            month.end,
        )
    )

    def item(m: Month) -> TrendMonth:
        txns = months.get(m, [])
        return TrendMonth(
            m,
            has_data(scope, m),
            summarize(txns, cur),
            spending_by_category(txns, cur),
            is_partial=m == current,
        )

    items = [item(first.shift(i)) for i in range(count)]
    with_data = [i for i in items if i.has_data]
    complete = [i for i in with_data if not i.is_partial]
    by_key = {i.month: i for i in items}
    averaged_months = [last_complete.shift(-k) for k in range(count)]
    averaged = [i for i in (by_key.get(m) or item(m) for m in averaged_months) if i.has_data]
    zero = Money.zero(cur)
    total_saved, total_inflow, total_spent = zero, zero, zero
    for i in with_data:
        total_saved = total_saved + i.summary.saved
        total_inflow = total_inflow + i.summary.inflow
        total_spent = total_spent + i.summary.spent
    return Trends(
        currency=cur,
        months=items,
        total_saved=total_saved,
        total_inflow=total_inflow,
        total_spent=total_spent,
        average_spent=average([i.summary.spent for i in averaged], cur),
        average_saved=average([i.summary.saved for i in averaged], cur),
        saving_rate=saving_rate(
            Summary(total_spent, total_inflow, Money.zero(cur), Money.zero(cur))
        ),
        best=max(complete, key=lambda i: i.summary.saved.amount) if complete else None,
        worst=min(complete, key=lambda i: i.summary.saved.amount) if complete else None,
    )
