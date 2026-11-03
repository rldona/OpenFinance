"""Repositorio de avisos descartados (OF-1301)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from openfinance.domain.shared.ids import UserId
from openfinance.infrastructure.db.models import AlertDismissalRow
from openfinance.infrastructure.db.repositories._common import _flush


class SqlAlertRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def dismissed(self, user_id: UserId) -> set[str]:
        return set(
            self._s.scalars(
                select(AlertDismissalRow.key).where(AlertDismissalRow.user_id == user_id)
            )
        )

    def dismiss(self, user_id: UserId, key: str, at: datetime) -> None:
        if self._s.get(AlertDismissalRow, (user_id, key)) is None:
            self._s.add(AlertDismissalRow(user_id=user_id, key=key, dismissed_at=at))
            _flush(self._s)
