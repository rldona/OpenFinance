"""Repositorio de informes a medida guardados (ADR-0025, OF-1503)."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from openfinance.domain.reports import SavedReport, from_dict, to_dict
from openfinance.domain.shared.ids import UserId, WorkspaceId
from openfinance.infrastructure.db.models import SavedReportRow
from openfinance.infrastructure.db.repositories._common import _as_utc, _flush


def _domain(row: SavedReportRow) -> SavedReport:
    return SavedReport(
        id=row.id,
        household_id=WorkspaceId(row.household_id),
        owner_id=UserId(row.owner_id),
        name=row.name,
        definition=from_dict(json.loads(row.definition)),
        shared=row.shared,
        created_at=_as_utc(row.created_at),
    )


class SqlSavedReportRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def visible_to(self, household_id: WorkspaceId, user_id: UserId) -> list[SavedReport]:
        rows = self._s.scalars(
            select(SavedReportRow)
            .where(
                SavedReportRow.household_id == household_id,
                or_(SavedReportRow.owner_id == user_id, SavedReportRow.shared.is_(True)),
            )
            .order_by(SavedReportRow.name, SavedReportRow.id)
        )
        return [_domain(r) for r in rows]

    def get(self, household_id: WorkspaceId, report_id: UUID) -> SavedReport | None:
        row = self._s.scalar(
            select(SavedReportRow).where(
                SavedReportRow.household_id == household_id, SavedReportRow.id == report_id
            )
        )
        return _domain(row) if row else None

    def count_owned(self, household_id: WorkspaceId, user_id: UserId) -> int:
        return int(
            self._s.scalar(
                select(func.count())
                .select_from(SavedReportRow)
                .where(
                    SavedReportRow.household_id == household_id, SavedReportRow.owner_id == user_id
                )
            )
            or 0
        )

    def add(self, report: SavedReport) -> None:
        self._s.add(
            SavedReportRow(
                id=report.id,
                household_id=report.household_id,
                owner_id=report.owner_id,
                name=report.name,
                definition=json.dumps(to_dict(report.definition)),
                shared=report.shared,
                created_at=report.created_at,
            )
        )
        _flush(self._s)

    def save(self, report: SavedReport) -> None:
        row = self._s.get(SavedReportRow, report.id)
        if row is None:
            raise LookupError(report.id)
        row.name = report.name
        row.definition = json.dumps(to_dict(report.definition))
        row.shared = report.shared
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, report_id: UUID) -> None:
        self._s.execute(
            delete(SavedReportRow).where(
                SavedReportRow.household_id == household_id, SavedReportRow.id == report_id
            )
        )
        _flush(self._s)
