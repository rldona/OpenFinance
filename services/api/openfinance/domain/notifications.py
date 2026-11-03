"""Notificaciones push: suscripciones, preferencias y el texto que sale (ADR-0023, OF-1302).

El texto de una notificación **nunca** lleva importes ni comercios: solo cuántos avisos hay y de
qué tipo. El detalle se ve dentro de la app, con la sesión iniciada.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlsplit

from openfinance.domain.alerts import Alert, AlertKind

MAX_ENDPOINT = 500
MAX_SUBSCRIPTIONS = 10
"""Dispositivos por persona."""
PUSH_HOSTS = (
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)
"""Los servicios push de los navegadores. El servidor solo envía a estos: el endpoint lo trae el
cliente y, sin lista, cualquier persona con sesión podría hacer que el servidor pida cualquier
URL (SSRF)."""


class NotificationError(ValueError):
    pass


class SendResult(StrEnum):
    SENT = "sent"
    GONE = "gone"
    """El servicio push dice que la suscripción ya no existe (404/410): se borra."""
    FAILED = "failed"
    """Fallo pasajero: se reintentará en la siguiente ejecución."""


@dataclass(frozen=True, slots=True)
class PushSubscription:
    endpoint: str
    p256dh: str
    auth: str

    def __post_init__(self) -> None:
        if not self.p256dh or not self.auth or len(self.p256dh) > 200 or len(self.auth) > 100:
            raise NotificationError("Suscripción no válida")
        if not is_push_endpoint(self.endpoint):
            raise NotificationError("Ese servicio de notificaciones no es compatible")


def is_push_endpoint(endpoint: str) -> bool:
    """Una URL https de un servicio push conocido (el host o un subdominio suyo)."""
    if not endpoint or len(endpoint) > MAX_ENDPOINT:
        return False
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        return False
    return any(host == h or host.endswith("." + h) for h in PUSH_HOSTS)


@dataclass(frozen=True, slots=True)
class NotificationPrefs:
    kinds: frozenset[AlertKind] = field(default_factory=lambda: frozenset(AlertKind))
    """Qué tipos de aviso se notifican."""
    weekly: bool = True
    """El resumen semanal (OF-1303)."""


@dataclass(frozen=True, slots=True)
class PushMessage:
    title: str
    body: str
    url: str
    tag: str


_LABEL = {
    AlertKind.LATE_PAYMENT: ("pago atrasado", "pagos atrasados"),
    AlertKind.LOW_BALANCE: ("saldo en negativo", "saldos en negativo"),
    AlertKind.BUDGET_OVER: ("presupuesto superado", "presupuestos superados"),
    AlertKind.DUPLICATE: ("posible duplicado", "posibles duplicados"),
    AlertKind.PRICE_RISE: ("subida de precio", "subidas de precio"),
    AlertKind.FEE: ("comisión", "comisiones"),
}


def digest_message(alerts: Iterable[Alert]) -> PushMessage | None:
    """Un único mensaje para todos los avisos nuevos, o ``None`` si no hay."""
    counts = Counter(a.kind for a in alerts)
    total = sum(counts.values())
    if total == 0:
        return None
    parts = [
        f"{n} {_LABEL[kind][0 if n == 1 else 1]}"
        for kind in AlertKind
        if (n := counts.get(kind, 0))
    ]
    title = "Tienes 1 aviso nuevo" if total == 1 else f"Tienes {total} avisos nuevos"
    return PushMessage(title, ", ".join(parts), "/#mes", "avisos")
