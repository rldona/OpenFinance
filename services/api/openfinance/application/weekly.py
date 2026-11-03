"""Resumen semanal para quien mira (ADR-0023, OF-1303).

Es una vista calculada, no un informe guardado. Cuenta los gastos de las cuentas que ve la
persona (ADR-0013), en la moneda del hogar, y lo mismo vale para los pagos y los avisos.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from openfinance.application.alerts import list_alerts
from openfinance.application.conversion import report_transactions
from openfinance.application.insights import shared_scope
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.application.schedule import list_schedule
from openfinance.domain.categories import CategoryId
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.schedule import Occurrence, OccurrenceStatus
from openfinance.domain.shared import Money
from openfinance.domain.weekly import (
    TOP_CATEGORIES,
    UPCOMING_DAYS,
    last_full_week,
    percent_change,
)
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class WeekCategory:
    category_id: CategoryId | None
    amount: Money


@dataclass(frozen=True, slots=True)
class UpcomingPayment:
    name: str
    occurrence: Occurrence


@dataclass(frozen=True, slots=True)
class WeeklySummary:
    start: date
    end: date
    spent: Money
    previous: Money
    change_percent: int | None
    top: list[WeekCategory]
    upcoming: list[UpcomingPayment]
    open_alerts: int


def _spent(txns: list[Transaction], zero: Money, start: date, end: date) -> Money:
    """Gasto neto entre dos días (ambos incluidos): una devolución resta."""
    total = zero
    for t in txns:
        if (
            not t.voided
            and t.kind is TransactionKind.EXPENSE
            and start <= t.booked_at.date() <= end
        ):
            total = total - t.amount
    return total


def _top(txns: list[Transaction], zero: Money, start: date, end: date) -> list[WeekCategory]:
    by_category: dict[CategoryId | None, Money] = defaultdict(lambda: zero)
    for t in txns:
        if (
            not t.voided
            and t.kind is TransactionKind.EXPENSE
            and start <= t.booked_at.date() <= end
        ):
            by_category[t.category_id] = by_category[t.category_id] - t.amount
    ranked = sorted(
        ((c, m) for c, m in by_category.items() if m.amount > 0),
        key=lambda item: (-item[1].amount, str(item[0])),
    )
    return [WeekCategory(c, m) for c, m in ranked[:TOP_CATEGORIES]]


def weekly_summary(uow: UnitOfWork, actor: Actor, today: date) -> WeeklySummary:
    start, end = last_full_week(today)
    previous_start, previous_end = last_full_week(start)
    zero = Money.zero(shared_scope(uow, actor).currency)
    accounts = [a.id for a in visible_accounts(uow, actor)]
    txns = (
        report_transactions(
            uow,
            actor.household_id,
            accounts,
            datetime.combine(previous_start, time.min),
            datetime.combine(end, time.max),
        )
        if accounts
        else []
    )
    spent = _spent(txns, zero, start, end)
    previous = _spent(txns, zero, previous_start, previous_end)
    limit = today + timedelta(days=UPCOMING_DAYS)
    upcoming = sorted(
        (
            UpcomingPayment(view.payment.name, o)
            for view in list_schedule(uow, actor, today, UPCOMING_DAYS)
            for o in view.occurrences
            if o.status is OccurrenceStatus.PENDING and o.due <= limit
        ),
        key=lambda u: (u.occurrence.due, u.name),
    )
    return WeeklySummary(
        start,
        end,
        spent,
        previous,
        percent_change(spent.amount, previous.amount),
        _top(txns, zero, start, end),
        upcoming,
        len(list_alerts(uow, actor, today)),
    )
