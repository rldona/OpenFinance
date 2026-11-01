"""Repositorios de categorías y reglas."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.categories import Category, CategoryId, CategoryRule
from openfinance.domain.shared.ids import (
    WorkspaceId,
)
from openfinance.infrastructure.db.models import (
    CategoryRow,
    CategoryRuleRow,
)
from openfinance.infrastructure.db.repositories._common import (
    _flush,
)


def _category(row: CategoryRow) -> Category:
    return Category(
        id=CategoryId(row.id),
        household_id=WorkspaceId(row.household_id),
        name=row.name,
        icon=row.icon,
        color=row.color,
        hidden=row.hidden,
        slug=row.slug,
        position=row.position,
    )


class SqlCategoryRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[Category]:
        rows = self._s.scalars(
            select(CategoryRow)
            .where(CategoryRow.household_id == household_id)
            .order_by(CategoryRow.position, CategoryRow.name)
        )
        return [_category(r) for r in rows]

    def get(self, household_id: WorkspaceId, category_id: CategoryId) -> Category | None:
        row = self._s.scalar(
            select(CategoryRow).where(
                CategoryRow.id == category_id, CategoryRow.household_id == household_id
            )
        )
        return _category(row) if row else None

    def add(self, category: Category) -> None:
        self._s.add(
            CategoryRow(
                id=category.id,
                household_id=category.household_id,
                name=category.name,
                key=category.key[:50],
                icon=category.icon,
                color=category.color,
                hidden=category.hidden,
                slug=category.slug,
                position=category.position,
            )
        )
        _flush(self._s)

    def update(self, category: Category) -> None:
        row = self._s.get(CategoryRow, category.id)
        if row is None or row.household_id != category.household_id:
            raise LookupError(category.id)
        row.name = category.name
        row.key = category.key[:50]
        row.icon = category.icon
        row.color = category.color
        row.hidden = category.hidden
        _flush(self._s)


class SqlRuleRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[CategoryRule]:
        rows = self._s.scalars(
            select(CategoryRuleRow).where(CategoryRuleRow.household_id == household_id)
        )
        return [
            CategoryRule(
                WorkspaceId(r.household_id), r.merchant, CategoryId(r.category_id), r.scope
            )
            for r in rows
        ]

    def upsert(self, rule: CategoryRule, now: datetime) -> None:
        row = self._s.get(CategoryRuleRow, (rule.household_id, rule.scope, rule.merchant))
        if row is None:
            self._s.add(
                CategoryRuleRow(
                    household_id=rule.household_id,
                    scope=rule.scope,
                    merchant=rule.merchant,
                    category_id=rule.category_id,
                    updated_at=now,
                )
            )
        else:
            row.category_id = rule.category_id
            row.updated_at = now
        _flush(self._s)

    def get(self, household_id: WorkspaceId, scope: str, merchant: str) -> CategoryRule | None:
        row = self._s.get(CategoryRuleRow, (household_id, scope, merchant))
        if row is None:
            return None
        return CategoryRule(
            WorkspaceId(row.household_id), row.merchant, CategoryId(row.category_id), row.scope
        )

    def delete(self, household_id: WorkspaceId, scope: str, merchant: str) -> None:
        self._s.execute(
            delete(CategoryRuleRow).where(
                CategoryRuleRow.household_id == household_id,
                CategoryRuleRow.scope == scope,
                CategoryRuleRow.merchant == merchant,
            )
        )
