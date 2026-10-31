"""Lote de importación: vista previa → confirmación (OF-105)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from openfinance.domain.shared.ids import AccountId, UserId, WorkspaceId

PREVIEW_TTL = timedelta(hours=24)
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_FILENAME = 150


class ImportStatus(StrEnum):
    PREVIEW = "preview"
    COMMITTED = "committed"


@dataclass(frozen=True, slots=True)
class ImportBatch:
    id: UUID
    household_id: WorkspaceId
    account_id: AccountId
    filename: str
    created_by: UserId
    created_at: datetime
    status: ImportStatus = ImportStatus.PREVIEW
    committed_at: datetime | None = None
    created_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0

    def is_expired(self, now: datetime) -> bool:
        return self.status is ImportStatus.PREVIEW and now - self.created_at > PREVIEW_TTL

    def committed(self, now: datetime, created: int, duplicates: int, skipped: int) -> ImportBatch:
        return replace(
            self,
            status=ImportStatus.COMMITTED,
            committed_at=now,
            created_count=created,
            duplicate_count=duplicates,
            skipped_count=skipped,
        )


def safe_filename(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    cleaned = "".join(c for c in base if c.isprintable())
    return (cleaned or "extracto")[:MAX_FILENAME]
