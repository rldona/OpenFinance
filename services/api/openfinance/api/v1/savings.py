from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    MONTH_PATTERN,
    BudgetIn,
    BudgetOut,
    BudgetsOut,
    CategoryAverageOut,
    GoalIn,
    GoalOut,
    GoalPatch,
    IdeaOut,
    MoneyOut,
    PriceChangeOut,
    RecurringOut,
    SavingsOverviewOut,
)
from openfinance.application import savings
from openfinance.application.savings import GoalInput
from openfinance.domain.categories import CategoryId, merchant_label
from openfinance.domain.insights import Month
from openfinance.domain.savings import GoalId
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId
from openfinance.infrastructure.time import local_today

router = APIRouter(tags=["savings"])


@router.get("/budgets", response_model=BudgetsOut)
def list_budgets(
    actor: ActorDep,
    uow: UowDep,
    month: Annotated[str | None, Query(pattern=MONTH_PATTERN)] = None,
) -> BudgetsOut:
    """Presupuestos mensuales con lo gastado en el mes (conjunta y huchas)."""
    m = Month.parse(month) if month else Month.of(local_today())
    views = savings.list_budgets(uow, actor, m, local_today())
    total_amount: Money | None = None
    total_spent: Money | None = None
    for v in views:
        total_amount = v.budget.amount if total_amount is None else total_amount + v.budget.amount
        total_spent = v.spent if total_spent is None else total_spent + v.spent
    return BudgetsOut(
        month=str(m),
        items=[BudgetOut.of(v) for v in views],
        total_amount=MoneyOut.of(total_amount) if total_amount else None,
        total_spent=MoneyOut.of(total_spent) if total_spent else None,
    )


@router.put("/budgets/{category_id}", response_model=BudgetOut)
def set_budget(category_id: UUID, body: BudgetIn, actor: ActorDep, uow: UowDep) -> BudgetOut:
    savings.set_budget(uow, actor, CategoryId(category_id), body.amount)
    views = savings.list_budgets(uow, actor, Month.of(local_today()), local_today())
    return BudgetOut.of(next(v for v in views if v.budget.category_id == category_id))


@router.delete("/budgets/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(category_id: UUID, actor: ActorDep, uow: UowDep) -> None:
    savings.delete_budget(uow, actor, CategoryId(category_id))


@router.get("/goals", response_model=list[GoalOut])
def list_goals(actor: ActorDep, uow: UowDep) -> list[GoalOut]:
    return [GoalOut.of(v) for v in savings.list_goals(uow, actor, local_today())]


@router.post("/goals", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(body: GoalIn, actor: ActorDep, uow: UowDep) -> GoalOut:
    data = GoalInput(
        name=body.name,
        icon=body.icon,
        target=body.target,
        monthly=body.monthly,
        saved=body.saved,
        deadline=body.deadline,
        account_id=AccountId(body.account_id) if body.account_id else None,
    )
    return GoalOut.of(savings.create_goal(uow, actor, data, local_today()))


@router.patch("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: UUID, body: GoalPatch, actor: ActorDep, uow: UowDep) -> GoalOut:
    data = GoalInput(
        name=body.name,
        icon=body.icon,
        target=body.target,
        monthly=body.monthly,
        saved=body.saved,
        deadline=body.deadline,
        account_id=AccountId(body.account_id) if body.account_id else None,
        clear_account=body.clear_account,
    )
    return GoalOut.of(savings.update_goal(uow, actor, GoalId(goal_id), data, local_today()))


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: UUID, actor: ActorDep, uow: UowDep) -> None:
    savings.delete_goal(uow, actor, GoalId(goal_id))


@router.put("/savings/ideas/{idea_id}/dismissed", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_idea(idea_id: str, actor: ActorDep, uow: UowDep) -> None:
    """Descarta una idea de ahorro para todo el hogar."""
    savings.set_idea_dismissed(uow, actor, idea_id, True, local_today())


@router.delete("/savings/ideas/{idea_id}/dismissed", status_code=status.HTTP_204_NO_CONTENT)
def restore_idea(idea_id: str, actor: ActorDep, uow: UowDep) -> None:
    """Recupera una idea descartada."""
    savings.set_idea_dismissed(uow, actor, idea_id, False, local_today())


@router.get("/savings/overview", response_model=SavingsOverviewOut)
def overview(actor: ActorDep, uow: UowDep) -> SavingsOverviewOut:
    """Todo lo de la pantalla Ahorrar: medias, cuotas, ideas y objetivos."""
    o = savings.savings_overview(uow, actor, local_today())
    return SavingsOverviewOut(
        month=str(o.month),
        months=[str(m) for m in o.months],
        average_saved=MoneyOut.of(o.average_saved) if o.average_saved else None,
        averages=[
            CategoryAverageOut(category_id=a.category_id, average=MoneyOut.of(a.average))
            for a in o.averages
        ],
        recurring=[
            RecurringOut(
                merchant=merchant_label(r.merchant),
                category_id=r.category_id,
                amount=MoneyOut.of(r.amount),
                first_amount=MoneyOut.of(r.first_amount),
                last_date=r.last_date,
                months=r.months,
                changes=[
                    PriceChangeOut(
                        month=str(c.month), before=MoneyOut.of(c.before), after=MoneyOut.of(c.after)
                    )
                    for c in r.changes
                ],
            )
            for r in o.recurring
        ],
        recurring_total=MoneyOut.of(o.recurring_total),
        ideas=[
            IdeaOut(
                id=i.id,
                icon=i.icon,
                title=i.title,
                detail=i.detail,
                yearly_saving=MoneyOut.of(i.yearly_saving),
                evidence=i.evidence,
                assumption=i.assumption,
                dismissed=i.id in o.dismissed_ideas,
            )
            for i in o.ideas
        ],
        goals=[GoalOut.of(g) for g in o.goals],
    )
