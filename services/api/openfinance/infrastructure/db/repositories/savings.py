"""Repositorios de presupuestos, objetivos e ideas descartadas."""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from openfinance.domain.categories import CategoryId
from openfinance.domain.insights import Month
from openfinance.domain.savings import Budget, Goal, GoalId
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import (
    AccountId,
    UserId,
    WorkspaceId,
)
from openfinance.infrastructure.db.models import (
    BudgetRow,
    DismissedIdeaRow,
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
            )
            for r in rows
        ]

    def upsert(self, budget: Budget) -> None:
        row = self._s.get(BudgetRow, (budget.household_id, budget.category_id))
        if row is None:
            self._s.add(
                BudgetRow(
                    household_id=budget.household_id,
                    category_id=budget.category_id,
                    amount=budget.amount.amount,
                    currency=budget.amount.currency.code,
                )
            )
        else:
            row.amount = budget.amount.amount
            row.currency = budget.amount.currency.code
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, category_id: CategoryId) -> None:
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

    def delete(self, household_id: WorkspaceId, goal_id: GoalId) -> None:
        self._s.execute(
            delete(GoalRow).where(GoalRow.id == goal_id, GoalRow.household_id == household_id)
        )
