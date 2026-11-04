"""Notificaciones push: dispositivos, preferencias y envío (ADR-0023, OF-1302).

Lo que se envía son los avisos que la persona ve (``list_alerts``), así que una cuenta personal
ajena no puede llegar a su móvil. Cada aviso se notifica una sola vez por persona.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from openfinance.application.alerts import list_alerts
from openfinance.application.errors import ConflictError, InvalidRequestError
from openfinance.application.ports import PushSender, UnitOfWork
from openfinance.domain.alerts import AlertKind
from openfinance.domain.notifications import (
    MAX_SUBSCRIPTIONS,
    NotificationError,
    NotificationPrefs,
    PushMessage,
    PushSubscription,
    SendResult,
    digest_message,
)
from openfinance.domain.shared.ids import UserId, WorkspaceId
from openfinance.domain.weekly import week_key
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class NotificationStatus:
    prefs: NotificationPrefs
    devices: int


def status(uow: UnitOfWork, actor: Actor) -> NotificationStatus:
    return NotificationStatus(
        uow.notifications.prefs(actor.user_id), len(uow.notifications.subscriptions(actor.user_id))
    )


def subscribe(
    uow: UnitOfWork, actor: Actor, endpoint: str, p256dh: str, auth: str, now: datetime
) -> None:
    try:
        subscription = PushSubscription(endpoint, p256dh, auth)
    except NotificationError as exc:
        raise InvalidRequestError(str(exc)) from exc
    known = uow.notifications.subscriptions(actor.user_id)
    if len(known) >= MAX_SUBSCRIPTIONS and endpoint not in {s.endpoint for s in known}:
        raise ConflictError(f"Ya hay {MAX_SUBSCRIPTIONS} dispositivos; quita alguno primero")
    uow.notifications.subscribe(actor.user_id, subscription, now)
    uow.commit()


def unsubscribe(uow: UnitOfWork, actor: Actor, endpoint: str) -> None:
    """Quita el dispositivo de esta persona. Es idempotente y no revela los de otras."""
    uow.notifications.unsubscribe(actor.user_id, endpoint)
    uow.commit()


def save_prefs(uow: UnitOfWork, actor: Actor, kinds: set[AlertKind], weekly: bool) -> None:
    uow.notifications.save_prefs(actor.user_id, NotificationPrefs(frozenset(kinds), weekly))
    uow.commit()


@dataclass(frozen=True, slots=True)
class NotifyReport:
    people: int = 0
    """Personas con algo que notificar."""
    sent: int = 0
    """Mensajes entregados al servicio push."""
    removed: int = 0
    """Dispositivos dados de baja porque el servicio push ya no los conoce."""
    failed: int = 0

    def __add__(self, other: NotifyReport) -> NotifyReport:
        return NotifyReport(
            self.people + other.people,
            self.sent + other.sent,
            self.removed + other.removed,
            self.failed + other.failed,
        )


WEEKLY_MESSAGE = PushMessage(
    "Tu resumen de la semana",
    "Ya está listo el resumen de la semana pasada.",
    "/#semana",
    "semana",
)


def _deliver(
    uow: UnitOfWork,
    sender: PushSender,
    user_id: UserId,
    message: PushMessage,
    keys: list[str],
    now: datetime,
) -> NotifyReport:
    """Manda un mensaje a todos los dispositivos de la persona. Solo si llega a alguno se da por
    notificado; si no, se reintenta en la siguiente ejecución."""
    sent = removed = failed = 0
    for device in uow.notifications.subscriptions(user_id):
        result = sender.send(device, message)
        if result is SendResult.SENT:
            sent += 1
        elif result is SendResult.GONE:
            uow.notifications.drop_endpoint(device.endpoint)
            removed += 1
        else:
            failed += 1
    if sent:
        uow.notifications.mark_delivered(user_id, keys, now)
    uow.commit()
    return NotifyReport(0, sent, removed, failed)


def _notify_person(
    uow: UnitOfWork,
    sender: PushSender,
    user_id: UserId,
    household_id: WorkspaceId,
    today: date,
    now: datetime,
) -> NotifyReport:
    if not uow.notifications.subscriptions(user_id):
        return NotifyReport()
    prefs = uow.notifications.prefs(user_id)
    actor = Actor(user_id, household_id)
    delivered = uow.notifications.delivered(user_id)
    report = NotifyReport()
    fresh = [
        a
        for a in list_alerts(uow, actor, today)
        if a.kind in prefs.kinds and a.key not in delivered
    ]
    message = digest_message(fresh)
    if message is not None:
        report = report + _deliver(uow, sender, user_id, message, [a.key for a in fresh], now)
    week = week_key(today)
    if prefs.weekly and week not in delivered and uow.notifications.subscriptions(user_id):
        report = report + _deliver(uow, sender, user_id, WEEKLY_MESSAGE, [week], now)
    if report.sent or report.removed or report.failed:
        report = report + NotifyReport(people=1)
    return report


def send_pending(uow: UnitOfWork, sender: PushSender, today: date, now: datetime) -> NotifyReport:
    """Notifica a cada persona sus avisos nuevos. Idempotente: lo ya enviado no se repite, y si
    ningún dispositivo lo recibe se reintenta en la siguiente ejecución."""
    report = NotifyReport()
    if not sender.enabled:
        return report
    for household_id in uow.households.all_ids():
        for member in uow.households.members(household_id):
            report = report + _notify_person(uow, sender, member.id, household_id, today, now)
    return report
