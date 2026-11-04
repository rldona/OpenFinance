"""Envío de Web Push con claves VAPID (OF-1302)."""

from __future__ import annotations

import base64
import json
import logging

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from openfinance.domain.notifications import PushMessage, PushSubscription, SendResult
from openfinance.infrastructure.config import Settings

log = logging.getLogger(__name__)
TTL_SECONDS = 24 * 3600
TIMEOUT_SECONDS = 10
GONE = (404, 410)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate_vapid_keys() -> tuple[str, str]:
    """Un par nuevo: (pública para el navegador, privada para el servidor), en base64 url."""
    vapid = Vapid()
    vapid.generate_keys()
    private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64(public), _b64(private)


class WebPushSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._vapid = (
            Vapid.from_raw(settings.vapid_private_key.encode()) if settings.push_enabled else None
        )

    @property
    def enabled(self) -> bool:
        return self._vapid is not None

    def send(self, subscription: PushSubscription, message: PushMessage) -> SendResult:
        if self._vapid is None:
            return SendResult.FAILED
        try:
            webpush(
                {
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps(
                    {
                        "title": message.title,
                        "body": message.body,
                        "url": message.url,
                        "tag": message.tag,
                    },
                    ensure_ascii=False,
                ),
                vapid_private_key=self._vapid,
                vapid_claims={"sub": self._settings.vapid_subject},
                ttl=TTL_SECONDS,
                timeout=TIMEOUT_SECONDS,
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in GONE:
                return SendResult.GONE
            log.warning("Web Push falló (estado %s)", status)
            return SendResult.FAILED
        except Exception:
            log.warning("Web Push falló (error de red)")
            return SendResult.FAILED
        return SendResult.SENT
