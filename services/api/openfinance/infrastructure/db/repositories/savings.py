"""Repositorios de presupuestos, objetivos e ideas descartadas."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from openfinance.domain.categories import CategoryId
from openfinance.domain.insights import Month
from openfinance.domain.savings import (
    Budget,
    BudgetMode,
    ContributionId,
    Goal,
    GoalContribution,
    GoalId,
)
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import (
    AccountId,
    UserId,
    WorkspaceId,
)
from openfinance.infrastructure.db.models import (
    BudgetOverrideRow,
    BudgetRow,
    DismissedIdeaRow,
    GoalContributionRow,
    GoalRow,
)
from openfinance.infrastructure.db.repositories._common import (
    _flush,
)


class SqlIdeaDismissalRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def dismissed(self, household_id: WorkspaceId) -> set[str]:
        return set(
            self._s.scalars(
                select(DismissedIdeaRow.idea_id).where(
                    DismissedIdeaRow.household_id == household_id
                )
            )
        )

    def dismiss(self, household_id: WorkspaceId, idea_id: str, user_id: UserId) -> None:
        if self._s.get(DismissedIdeaRow, (household_id, idea_id)) is None:
            self._s.add(
                DismissedIdeaRow(household_id=household_id, idea_id=idea_id, dismissed_by=user_id)
            )
            _flush(self._s)

    def restore(self, household_id: WorkspaceId, idea_id: str) -> None:
        self._s.execute(
            delete(DismissedIdeaRow).where(
                DismissedIdeaRow.household_id == household_id, DismissedIdeaRow.idea_id == idea_id
            )
        )
        _flush(self._s)


class SqlBudgetRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[Budget]:
        rows = self._s.scalars(select(BudgetRow).where(BudgetRow.household_id == household_id))
        return [
            Budget(
                WorkspaceId(r.household_id),
                CategoryId(r.category_id),
                Money.of(r.amount, r.currency),
                BudgetMode(r.mode),
                Month.parse(r.started) if r.started else None,
            )
            for r in rows
        ]

    def overrides(self, household_id: WorkspaceId) -> dict[tuple[CategoryId, Month], Money]:
        rows = self._s.scalars(
            select(BudgetOverrideRow).where(BudgetOverrideRow.household_id == household_id)
        )
        return {
            (CategoryId(r.category_id), Month.parse(r.month)): Money.of(r.amount, r.currency)
            for r in rows
        }

    def set_override(
        self, household_id: WorkspaceId, category_id: CategoryId, month: Month, amount: Money
    ) -> None:
        row = self._s.get(BudgetOverrideRow, (household_id, category_id, str(month)))
        if row is None:
            row = BudgetOverrideRow(
                household_id=household_id, category_id=category_id, month=str(month)
            )
            self._s.add(row)
        row.amount = amount.amount
        row.currency = amount.currency.code
        _flush(self._s)

    def delete_override(
        self, household_id: WorkspaceId, category_id: CategoryId, month: Month
    ) -> None:
        self._s.execute(
            delete(BudgetOverrideRow).where(
                BudgetOverrideRow.household_id == household_id,
                BudgetOverrideRow.category_id == category_id,
                BudgetOverrideRow.month == str(month),
            )
        )
        _flush(self._s)

    def upsert(self, budget: Budget) -> None:
        row = self._s.get(BudgetRow, (budget.household_id, budget.category_id))
        if row is None:
            self._s.add(
                BudgetRow(
                    household_id=budget.household_id,
                    category_id=budget.category_id,
                    amount=budget.amount.amount,
                    currency=budget.amount.currency.code,
                    mode=budget.mode.value,
                    started=str(budget.started) if budget.started else None,
                )
            )
        else:
            row.amount = budget.amount.amount
            row.currency = budget.amount.currency.code
            row.mode = budget.mode.value
            row.started = str(budget.started) if budget.started else None
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, category_id: CategoryId) -> None:
        self._s.execute(
            delete(BudgetOverrideRow).where(
                BudgetOverrideRow.household_id == household_id,
                BudgetOverrideRow.category_id == category_id,
            )
        )
        self._s.execute(
            delete(BudgetRow).where(
                BudgetRow.household_id == household_id, BudgetRow.category_id == category_id
            )
        )


def _goal(row: GoalRow) -> Goal:
    return Goal(
        id=GoalId(row.id),
        household_id=WorkspaceId(row.household_id),
        name=row.name,
        icon=row.icon,
        target=Money.of(row.target, row.currency),
        monthly=Money.of(row.monthly, row.currency),
        saved=Money.of(row.saved, row.currency),
        deadline=Month.parse(row.deadline) if row.deadline else None,
        account_id=AccountId(row.account_id) if row.account_id else None,
        priority=row.priority,
    )


def _contribution(row: GoalContributionRow) -> GoalContribution:
    return GoalContribution(
        id=ContributionId(row.id),
        household_id=WorkspaceId(row.household_id),
        goal_id=GoalId(row.goal_id),
        made_on=row.made_on,
        amount=Money.of(row.amount, row.currency),
        note=row.note,
    )


def _goal_values(goal: Goal) -> dict[str, object]:
    return {
        "name": goal.name,
        "icon": goal.icon,
        "target": goal.target.amount,
        "monthly": goal.monthly.amount,
        "saved": goal.saved.amount,
        "currency": goal.target.currency.code,
        "deadline": str(goal.deadline) if goal.deadline else None,
        "account_id": goal.account_id,
        "priority": goal.priority,
    }


class SqlGoalRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[Goal]:
        rows = self._s.scalars(
            select(GoalRow)
            .where(GoalRow.household_id == household_id)
            .order_by(GoalRow.created_at, GoalRow.name)
        )
        return [_goal(r) for r in rows]

    def get(self, household_id: WorkspaceId, goal_id: GoalId) -> Goal | None:
        row = self._s.scalar(
            select(GoalRow).where(GoalRow.id == goal_id, GoalRow.household_id == household_id)
        )
        return _goal(row) if row else None

    def add(self, goal: Goal) -> None:
        self._s.add(GoalRow(id=goal.id, household_id=goal.household_id, **_goal_values(goal)))
        _flush(self._s)

    def update(self, goal: Goal) -> None:
        self._s.execute(
            update(GoalRow)
            .where(GoalRow.id == goal.id, GoalRow.household_id == goal.household_id)
            .values(**_goal_values(goal))
        )
        _flush(self._s)

    def contributions(self, household_id: WorkspaceId, goal_id: GoalId) -> list[GoalContribution]:
        rows = self._s.scalars(
            select(GoalContributionRow)
            .where(
                GoalContributionRow.household_id == household_id,
                GoalContributionRow.goal_id == goal_id,
            )
            .order_by(GoalContributionRow.made_on.desc(), GoalContributionRow.created_at.desc())
        )
        return [_contribution(r) for r in rows]

    def contribution_totals(self, household_id: WorkspaceId) -> dict[GoalId, Money]:
        rows = self._s.execute(
            select(
                GoalContributionRow.goal_id,
                GoalContributionRow.currency,
                func.sum(GoalContributionRow.amount),
            )
            .where(GoalContributionRow.household_id == household_id)
            .group_by(GoalContributionRow.goal_id, GoalContributionRow.currency)
        )
        return {GoalId(goal_id): Money.of(total, currency) for goal_id, currency, total in rows}

    def get_contribution(
        self, household_id: WorkspaceId, contribution_id: UUID
    ) -> GoalContribution | None:
        row = self._s.scalar(
            select(GoalContributionRow).where(
                GoalContributionRow.id == contribution_id,
                GoalContributionRow.household_id == household_id,
            )
        )
        return _contribution(row) if row else None

    def save_contribution(self, contribution: GoalContribution, created_by: UserId) -> None:
        row = self._s.get(GoalContributionRow, contribution.id)
        if row is None:
            row = GoalContributionRow(
                id=contribution.id,
                household_id=contribution.household_id,
                created_by=created_by,
            )
            self._s.add(row)
        row.goal_id = contribution.goal_id
        row.made_on = contribution.made_on
        row.amount = contribution.amount.amount
        row.currency = contribution.amount.currency.code
        row.note = contribution.note
        _flush(self._s)

    def delete_contribution(self, household_id: WorkspaceId, contribution_id: UUID) -> None:
        self._s.execute(
            delete(GoalContributionRow).where(
                GoalContributionRow.id == contribution_id,
                GoalContributionRow.household_id == household_id,
            )
        )
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, goal_id: GoalId) -> None:
        self._s.execute(
            delete(GoalContributionRow).where(
                GoalContributionRow.goal_id == goal_id,
                GoalContributionRow.household_id == household_id,
            )
        )
        self._s.execute(
            delete(GoalRow).where(GoalRow.id == goal_id, GoalRow.household_id == household_id)
        )
