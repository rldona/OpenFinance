"""Repositorio de perfiles de CSV (OF-1105)."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.csv_profile import CsvProfile, build
from openfinance.domain.shared.ids import UserId, WorkspaceId
from openfinance.infrastructure.db.models import CsvProfileRow
from openfinance.infrastructure.db.repositories._common import _flush


def _profile(row: CsvProfileRow) -> CsvProfile:
    return build(row.id, WorkspaceId(row.household_id), row.name, json.loads(row.config))


class SqlCsvProfileRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[CsvProfile]:
        rows = self._s.scalars(
            select(CsvProfileRow)
            .where(CsvProfileRow.household_id == household_id)
            .order_by(CsvProfileRow.name)
        )
        return [_profile(r) for r in rows]

    def get(self, household_id: WorkspaceId, profile_id: UUID) -> CsvProfile | None:
        row = self._s.scalar(
            select(CsvProfileRow).where(
                CsvProfileRow.id == profile_id, CsvProfileRow.household_id == household_id
            )
        )
        return _profile(row) if row else None

    def save(self, profile: CsvProfile, created_by: UserId) -> None:
        row = self._s.get(CsvProfileRow, profile.id)
        if row is None:
            row = CsvProfileRow(
                id=profile.id, household_id=profile.household_id, created_by=created_by
            )
            self._s.add(row)
        row.name = profile.name
        row.config = json.dumps(profile.config(), sort_keys=True, ensure_ascii=False)
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, profile_id: UUID) -> None:
        self._s.execute(
            delete(CsvProfileRow).where(
                CsvProfileRow.id == profile_id, CsvProfileRow.household_id == household_id
            )
        )
        _flush(self._s)
