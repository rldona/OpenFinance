"""Repositorios de importaciones y patrones de recarga."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from openfinance.application.errors import ConflictError
from openfinance.domain.imports import MemberPattern, PatternDirection
from openfinance.domain.imports.batch import PREVIEW_TTL, ImportBatch, ImportStatus
from openfinance.domain.shared.ids import (
    AccountId,
    UserId,
    WorkspaceId,
)
from openfinance.infrastructure.db.models import (
    ImportBatchRow,
    MemberPatternRow,
)
from openfinance.infrastructure.db.repositories._common import (
    _as_utc,
    _flush,
)


def _batch(row: ImportBatchRow) -> ImportBatch:
    return ImportBatch(
        id=row.id,
        household_id=WorkspaceId(row.household_id),
        account_id=AccountId(row.account_id),
        filename=row.filename,
        created_by=UserId(row.created_by),
        created_at=_as_utc(row.created_at),
        status=ImportStatus(row.status),
        committed_at=_as_utc(row.committed_at) if row.committed_at else None,
        created_count=row.created_count,
        duplicate_count=row.duplicate_count,
        skipped_count=row.skipped_count,
        profile_id=row.profile_id,
    )


class SqlImportBatchRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, batch: ImportBatch, content: bytes) -> None:
        self._s.add(
            ImportBatchRow(
                id=batch.id,
                household_id=batch.household_id,
                account_id=batch.account_id,
                filename=batch.filename,
                content=content,
                status=batch.status.value,
                created_by=batch.created_by,
                created_at=batch.created_at,
                profile_id=batch.profile_id,
            )
        )
        self._s.flush()

    def get(self, household_id: WorkspaceId, batch_id: UUID) -> ImportBatch | None:
        row = self._s.scalar(
            select(ImportBatchRow).where(
                ImportBatchRow.id == batch_id, ImportBatchRow.household_id == household_id
            )
        )
        return _batch(row) if row else None

    def content(self, batch_id: UUID) -> bytes | None:
        return self._s.scalar(select(ImportBatchRow.content).where(ImportBatchRow.id == batch_id))

    def set_status(self, batch_id: UUID, status: ImportStatus) -> None:
        self._s.execute(
            update(ImportBatchRow).where(ImportBatchRow.id == batch_id).values(status=status.value)
        )

    def committed(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> list[ImportBatch]:
        """Confirmadas y deshechas de esas cuentas, de la más reciente a la más antigua."""
        if not account_ids:
            return []
        rows = self._s.scalars(
            select(ImportBatchRow)
            .where(
                ImportBatchRow.household_id == household_id,
                ImportBatchRow.account_id.in_(account_ids),
                ImportBatchRow.status != ImportStatus.PREVIEW.value,
            )
            .order_by(ImportBatchRow.committed_at.desc(), ImportBatchRow.created_at.desc())
        )
        return [_batch(r) for r in rows]

    def claim(self, batch_id: UUID) -> bool:
        result = self._s.execute(
            update(ImportBatchRow)
            .where(
                ImportBatchRow.id == batch_id,
                ImportBatchRow.status == ImportStatus.PREVIEW.value,
            )
            .values(status=ImportStatus.COMMITTED.value)
        )
        return bool(getattr(result, "rowcount", 0))

    def purge_expired_content(self, now: datetime) -> int:
        result = self._s.execute(
            update(ImportBatchRow)
            .where(
                ImportBatchRow.status == ImportStatus.PREVIEW.value,
                ImportBatchRow.created_at < now - PREVIEW_TTL,
                ImportBatchRow.content.is_not(None),
            )
            .values(content=None)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    def save_committed(self, batch: ImportBatch) -> None:
        row = self._s.get(ImportBatchRow, batch.id)
        if row is None:
            raise LookupError(batch.id)
        row.status = batch.status.value
        row.committed_at = batch.committed_at
        row.created_count = batch.created_count
        row.duplicate_count = batch.duplicate_count
        row.skipped_count = batch.skipped_count
        row.content = None
        self._s.flush()


class SqlMemberPatternRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[MemberPattern]:
        rows = self._s.scalars(
            select(MemberPatternRow)
            .where(MemberPatternRow.household_id == household_id)
            .order_by(MemberPatternRow.direction, MemberPatternRow.pattern)
        )
        return [
            MemberPattern(
                WorkspaceId(r.household_id),
                UserId(r.user_id),
                r.pattern,
                PatternDirection(r.direction),
            )
            for r in rows
        ]

    def add(self, pattern: MemberPattern, now: datetime) -> None:
        key = (pattern.household_id, pattern.direction.value, pattern.pattern)
        if self._s.get(MemberPatternRow, key) is not None:
            raise ConflictError("Ese patrón ya está guardado")
        self._s.add(
            MemberPatternRow(
                household_id=pattern.household_id,
                direction=pattern.direction.value,
                pattern=pattern.pattern,
                user_id=pattern.user_id,
                created_at=now,
            )
        )
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, direction: PatternDirection, pattern: str) -> bool:
        result = self._s.execute(
            delete(MemberPatternRow).where(
                MemberPatternRow.household_id == household_id,
                MemberPatternRow.direction == direction.value,
                MemberPatternRow.pattern == pattern,
            )
        )
        return bool(getattr(result, "rowcount", 0))
