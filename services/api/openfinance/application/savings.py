"""Presupuestos, objetivos, cuotas e ideas de ahorro (fase 4: OF-401..405).

Como los gráficos, todo se calcula solo con la conjunta y las huchas (ADR-0013).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from openfinance.application.errors import InvalidRequestError, NotFoundError
from openfinance.application.insights import shared_scope
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import Category, CategoryId
from openfinance.domain.insights import Month, average, by_month, spending_by_category
from openfinance.domain.ledger import AccountKind, account_balance, summarize
from openfinance.domain.savings import (
    Budget,
    BudgetStatus,
    CategoryStats,
    Goal,
    GoalId,
    GoalProjection,
    Idea,
    RecurringCharge,
    SavingsError,
    budget_status,
    build_ideas,
    detect_recurring,
    project_goal,
)
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId
from openfinance.domain.workspaces import Actor

HISTORY_MONTHS = 12


def _money(value: str, currency: Currency, what: str) -> Money:
    try:
        return Money.of(Decimal(value.strip().replace(",", ".")), currency)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidRequestError(f"{what}: importe no válido") from exc


def _currency(uow: UnitOfWork, actor: Actor) -> Currency:
    household = uow.households.get(actor.household_id)
    if household is None:
        raise NotFoundError("Hogar no encontrado")
    return household.currency


def _category(uow: UnitOfWork, actor: Actor, category_id: CategoryId) -> Category:
    category = uow.categories.get(actor.household_id, category_id)
    if category is None:
        raise NotFoundError("Categoría no encontrada")
    return category


# --- OF-401 · Presupuestos ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BudgetView:
    budget: Budget
    spent: Money
    percent: int
    status: BudgetStatus


def list_budgets(uow: UnitOfWork, actor: Actor, month: Month) -> list[BudgetView]:
    """Presupuestos con lo gastado en el mes (solo gastos de esa categoría y ese mes)."""
    scope = shared_scope(uow, actor)
    txns = uow.transactions.in_range(actor.household_id, scope.accounts, month.start, month.end)
    spent = spending_by_category(txns, scope.currency)
    order = {c.id: c.position for c in uow.categories.for_household(actor.household_id)}
    views = []
    for b in uow.budgets.for_household(actor.household_id):
        s = spent.get(b.category_id, Money.zero(scope.currency))
        percent, status = budget_status(s, b.amount)
        views.append(BudgetView(b, s, percent, status))
    views.sort(key=lambda v: order.get(v.budget.category_id, 1_000))
    return views


def set_budget(uow: UnitOfWork, actor: Actor, category_id: CategoryId, amount: str) -> Budget:
    _category(uow, actor, category_id)
    currency = _currency(uow, actor)
    try:
        budget = Budget(actor.household_id, category_id, _money(amount, currency, "Presupuesto"))
    except SavingsError as exc:
        raise InvalidRequestError(str(exc)) from exc
    uow.budgets.upsert(budget)
    uow.commit()
    return budget


def delete_budget(uow: UnitOfWork, actor: Actor, category_id: CategoryId) -> None:
    _category(uow, actor, category_id)
    uow.budgets.delete(actor.household_id, category_id)
    uow.commit()


# --- OF-402 · Objetivos ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GoalView:
    goal: Goal
    projection: GoalProjection


def _saved(uow: UnitOfWork, actor: Actor, goal: Goal) -> Money:
    if goal.account_id is None:
        return goal.saved
    account = next(
        (a for a in uow.accounts.for_household(actor.household_id) if a.id == goal.account_id), None
    )
    if account is None:
        return goal.saved
    balance = account_balance(account, uow.transactions.for_account(actor.household_id, account.id))
    return balance if not balance.is_negative else Money.zero(balance.currency)


def _check_account(uow: UnitOfWork, actor: Actor, account_id: AccountId | None) -> None:
    if account_id is None:
        return
    account = next(
        (a for a in uow.accounts.for_household(actor.household_id) if a.id == account_id), None
    )
    if account is None or account.kind is not AccountKind.SAVINGS:
        raise InvalidRequestError("Solo se puede vincular una hucha o cuenta de ahorro del hogar")


def list_goals(uow: UnitOfWork, actor: Actor, today: date) -> list[GoalView]:
    month = Month.of(today)
    return [
        GoalView(g, project_goal(g, _saved(uow, actor, g), month))
        for g in uow.goals.for_household(actor.household_id)
    ]


@dataclass(frozen=True, slots=True)
class GoalInput:
    name: str | None = None
    icon: str | None = None
    target: str | None = None
    monthly: str | None = None
    saved: str | None = None
    deadline: str | None = None
    """AAAA-MM o ``""`` para quitarla."""
    account_id: AccountId | None = None
    clear_account: bool = False


def _apply(goal: Goal, data: GoalInput, currency: Currency) -> Goal:
    deadline = goal.deadline
    if data.deadline is not None:
        try:
            deadline = Month.parse(data.deadline) if data.deadline else None
        except ValueError as exc:
            raise InvalidRequestError("Fecha límite no válida (AAAA-MM)") from exc
    try:
        return replace(
            goal,
            name=data.name.strip() if data.name is not None else goal.name,
            icon=data.icon.strip() if data.icon is not None else goal.icon,
            target=_money(data.target, currency, "Meta")
            if data.target is not None
            else goal.target,
            monthly=_money(data.monthly, currency, "Aportación")
            if data.monthly is not None
            else goal.monthly,
            saved=_money(data.saved, currency, "Ahorrado")
            if data.saved is not None
            else goal.saved,
            deadline=deadline,
            account_id=None if data.clear_account else (data.account_id or goal.account_id),
        )
    except SavingsError as exc:
        raise InvalidRequestError(str(exc)) from exc


def create_goal(uow: UnitOfWork, actor: Actor, data: GoalInput, today: date) -> GoalView:
    currency = _currency(uow, actor)
    if data.name is None or data.target is None:
        raise InvalidRequestError("El objetivo necesita nombre y meta")
    _check_account(uow, actor, data.account_id)
    try:
        base = Goal(
            id=GoalId(uuid4()),
            household_id=actor.household_id,
            name=data.name.strip() or "Objetivo",
            icon="🎯",
            target=_money(data.target, currency, "Meta"),
            monthly=Money.zero(currency),
            saved=Money.zero(currency),
        )
    except SavingsError as exc:
        raise InvalidRequestError(str(exc)) from exc
    goal = _apply(base, data, currency)
    uow.goals.add(goal)
    uow.commit()
    return GoalView(goal, project_goal(goal, _saved(uow, actor, goal), Month.of(today)))


def update_goal(
    uow: UnitOfWork, actor: Actor, goal_id: GoalId, data: GoalInput, today: date
) -> GoalView:
    current = uow.goals.get(actor.household_id, goal_id)
    if current is None:
        raise NotFoundError("Objetivo no encontrado")
    _check_account(uow, actor, data.account_id)
    goal = _apply(current, data, _currency(uow, actor))
    uow.goals.update(goal)
    uow.commit()
    return GoalView(goal, project_goal(goal, _saved(uow, actor, goal), Month.of(today)))


def delete_goal(uow: UnitOfWork, actor: Actor, goal_id: GoalId) -> None:
    if uow.goals.get(actor.household_id, goal_id) is None:
        raise NotFoundError("Objetivo no encontrado")
    uow.goals.delete(actor.household_id, goal_id)
    uow.commit()


# --- OF-403/404/405 · Resumen de ahorro -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class CategoryAverage:
    category_id: CategoryId | None
    average: Money


FIRST_MONTH_MAX_START_DAY = 3
"""Si el primer movimiento importado es posterior a este día, ese mes está incompleto."""


@dataclass(frozen=True, slots=True)
class SavingsOverview:
    currency: Currency
    month: Month
    """Mes en curso según el servidor (zona horaria del hogar)."""
    months: list[Month]
    """Meses completos con datos usados para las medias (hasta 12). Excluye el mes en curso
    y el primer mes importado si empieza a mitad de mes. Vacío si aún no hay ninguno."""
    average_saved: Money | None
    averages: list[CategoryAverage]
    """Gasto medio mensual por categoría: base del simulador."""
    recurring: list[RecurringCharge]
    recurring_total: Money
    ideas: list[Idea]
    goals: list[GoalView]


def savings_overview(uow: UnitOfWork, actor: Actor, today: date) -> SavingsOverview:
    scope = shared_scope(uow, actor)
    cur = scope.currency
    current = Month.of(today)
    first = uow.transactions.first_booked_at(actor.household_id, scope.accounts)
    first_complete = scope.first
    if first is not None and scope.first is not None and first.day > FIRST_MONTH_MAX_START_DAY:
        first_complete = scope.first.shift(1)
    candidates = [current.shift(-i) for i in range(1, HISTORY_MONTHS + 1)]
    months = sorted(m for m in candidates if first_complete is not None and m >= first_complete)
    start = current.shift(-HISTORY_MONTHS)
    txns = uow.transactions.in_range(actor.household_id, scope.accounts, start.start, current.end)
    grouped = by_month(txns)

    per_month = [spending_by_category(grouped.get(m, []), cur) for m in months]
    keys = {k for p in per_month for k in p}
    averages: list[CategoryAverage] = []
    stats: dict[str, CategoryStats] = {}
    slugs = {c.id: c.slug for c in uow.categories.for_household(actor.household_id)}
    in_period = [t for m in months for t in grouped.get(m, [])]
    for k in keys:
        values = [p.get(k, Money.zero(cur)) for p in per_month]
        avg = average(values, cur)
        if avg is None:
            continue
        averages.append(CategoryAverage(k, avg))
        slug = slugs.get(k) if k else None
        if slug:
            stats[slug] = CategoryStats(
                average=avg,
                count=sum(1 for t in in_period if t.category_id == k and t.amount.is_negative),
                min_month=min(values, key=lambda v: v.amount),
                max_month=max(values, key=lambda v: v.amount),
            )
    averages.sort(key=lambda a: -a.average.amount)

    recurring = detect_recurring(txns, cur, today)
    total = Money.zero(cur)
    for r in recurring:
        total = total + r.amount
    subscriptions = [
        r for r in recurring if r.category_id and slugs.get(r.category_id) == "suscripciones"
    ]

    saved = [summarize(grouped.get(m, []), cur).saved for m in months]
    return SavingsOverview(
        currency=cur,
        month=current,
        months=months,
        average_saved=average(saved, cur),
        averages=averages,
        recurring=recurring,
        recurring_total=total,
        ideas=build_ideas(stats, recurring, subscriptions, len(months), cur),
        goals=list_goals(uow, actor, today),
    )
