"""Notificaciones push y sus preferencias (ADR-0023, OF-1302)."""

from fastapi import APIRouter, Response, status

from openfinance.api.deps import ActorDep, SettingsDep, UowDep
from openfinance.api.v1.schemas import (
    NotificationPrefsIn,
    NotificationsOut,
    PushEndpointIn,
    PushSubscriptionIn,
)
from openfinance.application import notifications
from openfinance.domain.alerts import AlertKind
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["notifications"])


def _out(actor: ActorDep, uow: UowDep, settings: SettingsDep) -> NotificationsOut:
    state = notifications.status(uow, actor)
    return NotificationsOut(
        configured=settings.push_enabled,
        public_key=settings.vapid_public_key if settings.push_enabled else None,
        devices=state.devices,
        kinds=sorted(k.value for k in state.prefs.kinds),
        weekly=state.prefs.weekly,
    )


@router.get("/notifications", response_model=NotificationsOut)
def get_notifications(actor: ActorDep, uow: UowDep, settings: SettingsDep) -> NotificationsOut:
    return _out(actor, uow, settings)


@router.put("/notifications/preferences", response_model=NotificationsOut)
def save_preferences(
    body: NotificationPrefsIn, actor: ActorDep, uow: UowDep, settings: SettingsDep
) -> NotificationsOut:
    notifications.save_prefs(uow, actor, {AlertKind(k) for k in body.kinds}, body.weekly)
    return _out(actor, uow, settings)


@router.post("/notifications/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def subscribe(body: PushSubscriptionIn, actor: ActorDep, uow: UowDep) -> Response:
    notifications.subscribe(uow, actor, body.endpoint, body.keys.p256dh, body.keys.auth, utc_now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notifications/subscriptions/remove", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(body: PushEndpointIn, actor: ActorDep, uow: UowDep) -> Response:
    notifications.unsubscribe(uow, actor, body.endpoint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
