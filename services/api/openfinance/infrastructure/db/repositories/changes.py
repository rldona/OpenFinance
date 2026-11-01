"""Repositorio del registro de cambios (ADR-0017)."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from openfinance.domain.changes import Change, Entity, Operation
from openfinance.domain.shared.ids import (
    UserId,
    WorkspaceId,
)
from openfinance.infrastructure.db.models import (
    ChangeEntryRow,
    ChangeOperationRow,
)
from openfinance.infrastructure.db.repositories._common import (
    _as_utc,
    _flush,
)


def _operation(row: ChangeOperationRow, entries: list[ChangeEntryRow]) -> Operation:
    return Operation(
        id=row.id,
        household_id=WorkspaceId(row.household_id),
        actor_id=UserId(row.actor_id),
        created_at=_as_utc(row.created_at),
        action=row.action,
        summary=row.summary,
        changes=tuple(
            Change(
                Entity(e.entity), e.entity_id, e.field, json.loads(e.before), json.loads(e.after)
            )
            for e in sorted(entries, key=lambda e: e.position)
        ),
        undone_at=_as_utc(row.undone_at) if row.undone_at else None,
        undone_by=UserId(row.undone_by) if row.undone_by else None,
    )


class SqlChangeRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, operation: Operation) -> None:
        o = operation
        self._s.add(
            ChangeOperationRow(
                id=o.id,
                household_id=o.household_id,
                actor_id=o.actor_id,
                created_at=o.created_at,
                action=o.action,
                summary=o.summary,
            )
        )
        self._s.flush()
        self._s.add_all(
            ChangeEntryRow(
                operation_id=o.id,
                position=i,
                entity=c.entity.value,
                entity_id=c.entity_id,
                field=c.field,
                before=json.dumps(c.before),
                after=json.dumps(c.after),
            )
            for i, c in enumerate(o.changes)
        )
        _flush(self._s)

    def _entries(self, ids: list[UUID]) -> dict[UUID, list[ChangeEntryRow]]:
        out: dict[UUID, list[ChangeEntryRow]] = {i: [] for i in ids}
        for i in range(0, len(ids), 500):
            for e in self._s.scalars(
                select(ChangeEntryRow).where(ChangeEntryRow.operation_id.in_(ids[i : i + 500]))
            ):
                out[e.operation_id].append(e)
        return out

    def get(self, household_id: WorkspaceId, operation_id: UUID) -> Operation | None:
        row = self._s.scalar(
            select(ChangeOperationRow).where(
                ChangeOperationRow.id == operation_id,
                ChangeOperationRow.household_id == household_id,
            )
        )
        return _operation(row, self._entries([row.id])[row.id]) if row else None

    def for_actor(self, household_id: WorkspaceId, actor_id: UserId, limit: int) -> list[Operation]:
        rows = list(
            self._s.scalars(
                select(ChangeOperationRow)
                .where(
                    ChangeOperationRow.household_id == household_id,
                    ChangeOperationRow.actor_id == actor_id,
                )
                .order_by(ChangeOperationRow.created_at.desc())
                .limit(limit)
            )
        )
        entries = self._entries([r.id for r in rows])
        return [_operation(r, entries[r.id]) for r in rows]

    def touching(
        self, household_id: WorkspaceId, entity: Entity, entity_ids: list[str]
    ) -> list[Operation]:
        """Operaciones que cambian alguna de esas entidades, de la más antigua a la más reciente."""
        if not entity_ids:
            return []
        op_ids: set[UUID] = set()
        for i in range(0, len(entity_ids), 500):
            op_ids.update(
                self._s.scalars(
                    select(ChangeEntryRow.operation_id)
                    .join(ChangeOperationRow, ChangeOperationRow.id == ChangeEntryRow.operation_id)
                    .where(
                        ChangeOperationRow.household_id == household_id,
                        ChangeEntryRow.entity == entity.value,
                        ChangeEntryRow.entity_id.in_(entity_ids[i : i + 500]),
                    )
                )
            )
        if not op_ids:
            return []
        rows = list(
            self._s.scalars(
                select(ChangeOperationRow)
                .where(ChangeOperationRow.id.in_(op_ids))
                .order_by(ChangeOperationRow.created_at)
            )
        )
        entries = self._entries([r.id for r in rows])
        return [_operation(r, entries[r.id]) for r in rows]

    def mark_undone(
        self, operation_id: UUID, undone_at: datetime | None, undone_by: UserId | None
    ) -> None:
        self._s.execute(
            update(ChangeOperationRow)
            .where(ChangeOperationRow.id == operation_id)
            .values(undone_at=undone_at, undone_by=undone_by)
        )
