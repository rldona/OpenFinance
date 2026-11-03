"""Repositorio de notificaciones push (OF-1302)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.alerts import AlertKind
from openfinance.domain.notifications import NotificationPrefs, PushSubscription
from openfinance.domain.shared.ids import UserId
from openfinance.infrastructure.db.models import (
    AlertDeliveryRow,
    NotificationPrefRow,
    PushSubscriptionRow,
)
from openfinance.infrastructure.db.repositories._common import _flush


class SqlNotificationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def subscriptions(self, user_id: UserId) -> list[PushSubscription]:
        rows = self._s.scalars(
            select(PushSubscriptionRow)
            .where(PushSubscriptionRow.user_id == user_id)
            .order_by(PushSubscriptionRow.created_at, PushSubscriptionRow.id)
        )
        return [PushSubscription(r.endpoint, r.p256dh, r.auth) for r in rows]

    def subscribe(self, user_id: UserId, subscription: PushSubscription, at: datetime) -> None:
        row = self._s.scalar(
            select(PushSubscriptionRow).where(PushSubscriptionRow.endpoint == subscription.endpoint)
        )
        if row is None:
            row = PushSubscriptionRow(id=uuid4(), endpoint=subscription.endpoint, created_at=at)
            self._s.add(row)
        row.user_id = user_id
        row.p256dh = subscription.p256dh
        row.auth = subscription.auth
        _flush(self._s)

    def unsubscribe(self, user_id: UserId, endpoint: str) -> bool:
        result = self._s.execute(
            delete(PushSubscriptionRow).where(
                PushSubscriptionRow.user_id == user_id, PushSubscriptionRow.endpoint == endpoint
            )
        )
        _flush(self._s)
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def drop_endpoint(self, endpoint: str) -> None:
        self._s.execute(delete(PushSubscriptionRow).where(PushSubscriptionRow.endpoint == endpoint))
        _flush(self._s)

    def prefs(self, user_id: UserId) -> NotificationPrefs:
        row = self._s.get(NotificationPrefRow, user_id)
        if row is None:
            return NotificationPrefs()
        kinds = frozenset(AlertKind(k) for k in row.kinds.split(",") if k)
        return NotificationPrefs(kinds, row.weekly)

    def save_prefs(self, user_id: UserId, prefs: NotificationPrefs) -> None:
        row = self._s.get(NotificationPrefRow, user_id)
        if row is None:
            row = NotificationPrefRow(user_id=user_id)
            self._s.add(row)
        row.kinds = ",".join(sorted(k.value for k in prefs.kinds))
        row.weekly = prefs.weekly
        _flush(self._s)

    def delivered(self, user_id: UserId) -> set[str]:
        return set(
            self._s.scalars(select(AlertDeliveryRow.key).where(AlertDeliveryRow.user_id == user_id))
        )

    def mark_delivered(self, user_id: UserId, keys: list[str], at: datetime) -> None:
        known = self.delivered(user_id)
        for key in keys:
            if key not in known:
                self._s.add(AlertDeliveryRow(user_id=user_id, key=key, delivered_at=at))
        _flush(self._s)
