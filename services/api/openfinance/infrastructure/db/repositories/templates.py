"""Repositorio de plantillas de movimientos (OF-1204)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.shared.ids import UserId, WorkspaceId
from openfinance.domain.templates import TransactionTemplate, from_definition
from openfinance.infrastructure.db.models import TransactionTemplateRow
from openfinance.infrastructure.db.repositories._common import _flush


def _template(row: TransactionTemplateRow) -> TransactionTemplate:
    return from_definition(row.id, WorkspaceId(row.household_id), row.definition)


class SqlTemplateRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[TransactionTemplate]:
        rows = self._s.scalars(
            select(TransactionTemplateRow)
            .where(TransactionTemplateRow.household_id == household_id)
            .order_by(TransactionTemplateRow.name, TransactionTemplateRow.created_at)
        )
        return [_template(r) for r in rows]

    def get(self, household_id: WorkspaceId, template_id: UUID) -> TransactionTemplate | None:
        row = self._s.scalar(
            select(TransactionTemplateRow).where(
                TransactionTemplateRow.id == template_id,
                TransactionTemplateRow.household_id == household_id,
            )
        )
        return _template(row) if row else None

    def save(self, template: TransactionTemplate, created_by: UserId) -> None:
        row = self._s.get(TransactionTemplateRow, template.id)
        if row is None:
            row = TransactionTemplateRow(
                id=template.id, household_id=template.household_id, created_by=created_by
            )
            self._s.add(row)
        row.scope = template.scope
        row.name = template.name
        row.definition = template.definition()
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, template_id: UUID) -> None:
        self._s.execute(
            delete(TransactionTemplateRow).where(
                TransactionTemplateRow.id == template_id,
                TransactionTemplateRow.household_id == household_id,
            )
        )
        _flush(self._s)
