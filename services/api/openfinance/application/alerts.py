"""Avisos del hogar para quien mira (ADR-0023, OF-1301).

Cada detector solo ve lo que ve la persona (ADR-0013): una cuenta personal ajena no genera
avisos ni se cuela en los de la conjunta. Los avisos se recalculan en cada consulta; solo se
guarda, por persona, cuáles ha descartado.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from openfinance.application.conversion import report_transactions
from openfinance.application.errors import NotFoundError
from openfinance.application.forecast import household_forecast
from openfinance.application.insights import shared_scope
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.application.savings import HISTORY_MONTHS, list_budgets
from openfinance.application.schedule import list_schedule
from openfinance.domain.alerts import (
    DUPLICATE_DAYS,
    FEE_DAYS,
    LOW_BALANCE_DAYS,
    RECENT_DAYS,
    Alert,
    AlertKind,
    Severity,
    consents,
    duplicates,
    fees,
    price_rises,
    sort_alerts,
)
from openfinance.domain.insights import Month
from openfinance.domain.savings import BudgetStatus, detect_recurring
from openfinance.domain.schedule import OccurrenceStatus
from openfinance.domain.workspaces import Actor

LOOKBACK_DAYS = max(RECENT_DAYS + DUPLICATE_DAYS, FEE_DAYS)


def _late_payments(uow: UnitOfWork, actor: Actor, today: date) -> list[Alert]:
    found: list[Alert] = []
    for view in list_schedule(uow, actor, today, 1):
        for o in view.occurrences:
            if o.status is not OccurrenceStatus.LATE:
                continue
            found.append(
                Alert(
                    AlertKind.LATE_PAYMENT,
                    f"late_payment:{view.payment.id}:{o.due.isoformat()}",
                    Severity.WARNING,
                    f"{view.payment.name} no ha llegado",
                    f"Se esperaba el {o.due.isoformat()} y no hay ningún movimiento que lo cumpla.",
                    o.due,
                    -o.amount if o.amount.is_negative else o.amount,
                    str(view.payment.account_id),
                )
            )
    return found


def _low_balance(uow: UnitOfWork, actor: Actor, today: date) -> list[Alert]:
    found: list[Alert] = []
    for item in household_forecast(uow, actor, today, LOW_BALANCE_DAYS).accounts:
        day = item.forecast.first_negative
        if day is None:
            continue
        found.append(
            Alert(
                AlertKind.LOW_BALANCE,
                f"low_balance:{item.account.id}:{day.isoformat()}",
                Severity.CRITICAL,
                f"{item.account.name} se queda en negativo",
                f"Según los pagos programados, el {day.isoformat()}. "
                f"Mínimo previsto: {item.forecast.lowest.balance.amount:.2f} "
                f"{item.account.currency.code}.",
                day,
                item.forecast.lowest.balance,
                str(item.account.id),
            )
        )
    return found


def _budgets(uow: UnitOfWork, actor: Actor, today: date) -> list[Alert]:
    month = Month.of(today)
    found: list[Alert] = []
    for view in list_budgets(uow, actor, month, today):
        if view.status is not BudgetStatus.OVER:
            continue
        category = uow.categories.get(actor.household_id, view.budget.category_id)
        name = category.name if category else "Categoría"
        found.append(
            Alert(
                AlertKind.BUDGET_OVER,
                f"budget_over:{view.budget.category_id}:{month}",
                Severity.WARNING,
                f"Presupuesto de {name} superado",
                f"Gastado {view.spent.amount:.2f} de {view.limit.amount:.2f} "
                f"{view.limit.currency.code} este mes.",
                today,
                view.spent - view.limit,
            )
        )
    return found


def _recurring(uow: UnitOfWork, actor: Actor, today: date) -> list[Alert]:
    scope = shared_scope(uow, actor)
    if not scope.accounts:
        return []
    month = Month.of(today)
    txns = report_transactions(
        uow, actor.household_id, scope.accounts, month.shift(-HISTORY_MONTHS).start, month.end
    )
    return price_rises(detect_recurring(txns, scope.currency, today), today)


def _movements(uow: UnitOfWork, actor: Actor, today: date) -> list[Alert]:
    ids = [a.id for a in visible_accounts(uow, actor)]
    if not ids:
        return []
    start = datetime.combine(today - timedelta(days=LOOKBACK_DAYS), time.min)
    end = datetime.combine(today, time.max)
    txns = uow.transactions.in_range(actor.household_id, ids, start, end)
    return [*duplicates(txns, today), *fees(txns, today)]


def _consents(uow: UnitOfWork, actor: Actor, today: date) -> list[Alert]:
    """Solo las conexiones de quien mira: el consentimiento es personal (ADR-0024)."""
    return consents(uow.bank.for_owner(actor.household_id, actor.user_id), today)


def current_alerts(uow: UnitOfWork, actor: Actor, today: date) -> list[Alert]:
    """Todos los avisos de hoy para esta persona, incluidos los que ya descartó."""
    return sort_alerts(
        [
            *_low_balance(uow, actor, today),
            *_late_payments(uow, actor, today),
            *_budgets(uow, actor, today),
            *_recurring(uow, actor, today),
            *_movements(uow, actor, today),
            *_consents(uow, actor, today),
        ]
    )


def list_alerts(uow: UnitOfWork, actor: Actor, today: date) -> list[Alert]:
    """Los avisos de hoy que esta persona no ha descartado."""
    dismissed = uow.alerts.dismissed(actor.user_id)
    return [a for a in current_alerts(uow, actor, today) if a.key not in dismissed]


def dismiss_alert(uow: UnitOfWork, actor: Actor, key: str, today: date, now: datetime) -> None:
    """Descarta un aviso para esta persona. Solo se pueden descartar avisos que existen hoy
    y que ve: así una clave inventada, o de la cuenta personal de otra persona, da 404."""
    if key not in {a.key for a in current_alerts(uow, actor, today)}:
        raise NotFoundError("Aviso no encontrado")
    uow.alerts.dismiss(actor.user_id, key, now)
    uow.commit()
