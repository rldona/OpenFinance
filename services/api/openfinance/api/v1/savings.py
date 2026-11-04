from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    AMOUNT_PATTERN,
    MONTH_PATTERN,
    BudgetIn,
    BudgetMonthIn,
    BudgetOut,
    BudgetsOut,
    CategoryAverageOut,
    ContributionChangeOut,
    ContributionIn,
    ContributionOut,
    GoalIn,
    GoalOut,
    GoalPatch,
    IdeaOut,
    MoneyOut,
    OperationRefOut,
    PriceChangeOut,
    RecurringOut,
    SavingsOverviewOut,
    ShareOut,
)
from openfinance.application import savings
from openfinance.application.savings import GoalInput
from openfinance.domain.categories import CategoryId, merchant_label
from openfinance.domain.insights import Month
from openfinance.domain.savings import GoalId
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId
from openfinance.infrastructure.time import local_today, utc_now

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
        total_amount = v.limit if total_amount is None else total_amount + v.limit
        total_spent = v.spent if total_spent is None else total_spent + v.spent
    return BudgetsOut(
        month=str(m),
        items=[BudgetOut.of(v) for v in views],
        total_amount=MoneyOut.of(total_amount) if total_amount else None,
        total_spent=MoneyOut.of(total_spent) if total_spent else None,
    )


@router.put("/budgets/{category_id}", response_model=BudgetOut)
def set_budget(category_id: UUID, body: BudgetIn, actor: ActorDep, uow: UowDep) -> BudgetOut:
    started = Month.parse(body.started) if body.started else None
    savings.set_budget(
        uow, actor, CategoryId(category_id), body.amount, body.mode, local_today(), started
    )
    views = savings.list_budgets(uow, actor, Month.of(local_today()), local_today())
    return BudgetOut.of(next(v for v in views if v.budget.category_id == category_id))


@router.put("/budgets/{category_id}/months/{month}", response_model=BudgetOut)
def set_month_amount(
    category_id: UUID,
    body: BudgetMonthIn,
    actor: ActorDep,
    uow: UowDep,
    month: Annotated[str, Path(pattern=MONTH_PATTERN)],
) -> BudgetOut:
    """Un importe propio para un mes (OF-1203). Devuelve el presupuesto de ese mes."""
    m = Month.parse(month)
    savings.set_month_amount(uow, actor, CategoryId(category_id), m, body.amount)
    views = savings.list_budgets(uow, actor, m, local_today())
    return BudgetOut.of(next(v for v in views if v.budget.category_id == category_id))


@router.delete("/budgets/{category_id}/months/{month}", status_code=status.HTTP_204_NO_CONTENT)
def clear_month_amount(
    category_id: UUID,
    actor: ActorDep,
    uow: UowDep,
    month: Annotated[str, Path(pattern=MONTH_PATTERN)],
) -> None:
    savings.clear_month_amount(uow, actor, CategoryId(category_id), Month.parse(month))


@router.delete("/budgets/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(category_id: UUID, actor: ActorDep, uow: UowDep) -> None:
    savings.delete_budget(uow, actor, CategoryId(category_id))


@router.get("/goals/split", response_model=list[ShareOut])
def suggest_split(
    actor: ActorDep, uow: UowDep, amount: Annotated[str, Query(pattern=AMOUNT_PATTERN)]
) -> list[ShareOut]:
    """Cómo repartir una cantidad entre los objetivos, por prioridad (OF-1206). No apunta nada."""
    return [
        ShareOut(
            goal_id=s.goal.goal.id,
            name=s.goal.goal.name,
            amount=MoneyOut.of(s.amount),
            remaining=MoneyOut.of(s.goal.projection.remaining),
        )
        for s in savings.suggest_split(uow, actor, amount, local_today())
    ]


@router.get("/goals/{goal_id}/contributions", response_model=list[ContributionOut])
def list_contributions(goal_id: UUID, actor: ActorDep, uow: UowDep) -> list[ContributionOut]:
    return [ContributionOut.of(c) for c in savings.list_contributions(uow, actor, GoalId(goal_id))]


@router.post(
    "/goals/{goal_id}/contributions",
    response_model=ContributionChangeOut,
    status_code=status.HTTP_201_CREATED,
)
def add_contribution(
    goal_id: UUID, body: ContributionIn, actor: ActorDep, uow: UowDep
) -> ContributionChangeOut:
    """Anota una aportación (o, en negativo, una retirada) a un objetivo sin hucha."""
    contribution, operation_id = savings.add_contribution(
        uow,
        actor,
        GoalId(goal_id),
        body.amount,
        body.made_on or local_today(),
        body.note,
        utc_now(),
    )
    return ContributionChangeOut(
        contribution=ContributionOut.of(contribution), operation_id=operation_id
    )


@router.delete("/goals/{goal_id}/contributions/{contribution_id}", response_model=OperationRefOut)
def delete_contribution(
    goal_id: UUID, contribution_id: UUID, actor: ActorDep, uow: UowDep
) -> OperationRefOut:
    return OperationRefOut(
        operation_id=savings.delete_contribution(
            uow, actor, GoalId(goal_id), contribution_id, utc_now()
        )
    )


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
        priority=body.priority,
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
        priority=body.priority,
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
