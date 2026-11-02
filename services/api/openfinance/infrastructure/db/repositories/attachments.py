"""Repositorio de los metadatos de los adjuntos (OF-1007)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from openfinance.domain.attachments import Attachment
from openfinance.domain.shared.ids import TransactionId, UserId, WorkspaceId
from openfinance.infrastructure.db.models import AttachmentRow
from openfinance.infrastructure.db.repositories._common import _as_utc, _flush


def _attachment(r: AttachmentRow) -> Attachment:
    return Attachment(
        id=r.id,
        household_id=WorkspaceId(r.household_id),
        transaction_id=TransactionId(r.transaction_id),
        filename=r.filename,
        content_type=r.content_type,
        size=r.size,
        sha256=r.sha256,
        created_by=UserId(r.created_by),
        created_at=_as_utc(r.created_at),
        deleted_at=_as_utc(r.deleted_at) if r.deleted_at else None,
    )


class SqlAttachmentRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, attachment: Attachment) -> None:
        a = attachment
        self._s.add(
            AttachmentRow(
                id=a.id,
                household_id=a.household_id,
                transaction_id=a.transaction_id,
                filename=a.filename,
                content_type=a.content_type,
                size=a.size,
                sha256=a.sha256,
                created_by=a.created_by,
                created_at=a.created_at,
            )
        )
        _flush(self._s)

    def get(self, household_id: WorkspaceId, attachment_id: UUID) -> Attachment | None:
        row = self._s.scalar(
            select(AttachmentRow).where(
                AttachmentRow.id == attachment_id, AttachmentRow.household_id == household_id
            )
        )
        return _attachment(row) if row else None

    def for_transactions(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, list[Attachment]]:
        found: dict[TransactionId, list[Attachment]] = {}
        for i in range(0, len(ids), 500):
            rows = self._s.scalars(
                select(AttachmentRow)
                .where(
                    AttachmentRow.household_id == household_id,
                    AttachmentRow.transaction_id.in_(ids[i : i + 500]),
                    AttachmentRow.deleted_at.is_(None),
                )
                .order_by(AttachmentRow.created_at, AttachmentRow.id)
            )
            for r in rows:
                found.setdefault(TransactionId(r.transaction_id), []).append(_attachment(r))
        return found

    def set_deleted(
        self, household_id: WorkspaceId, attachment_id: UUID, deleted_at: datetime | None
    ) -> None:
        self._s.execute(
            update(AttachmentRow)
            .where(AttachmentRow.id == attachment_id, AttachmentRow.household_id == household_id)
            .values(deleted_at=deleted_at)
        )
        _flush(self._s)

    def deleted_before(self, cutoff: datetime) -> list[Attachment]:
        rows = self._s.scalars(
            select(AttachmentRow).where(
                AttachmentRow.deleted_at.is_not(None), AttachmentRow.deleted_at < cutoff
            )
        )
        return [_attachment(r) for r in rows]

    def erase(self, attachment_id: UUID) -> None:
        self._s.execute(delete(AttachmentRow).where(AttachmentRow.id == attachment_id))
        _flush(self._s)
