"""OF-1302: el texto de una notificación y qué endpoints se aceptan."""

from datetime import date

import pytest

from openfinance.domain.alerts import Alert, AlertKind, Severity
from openfinance.domain.notifications import (
    NotificationError,
    PushSubscription,
    digest_message,
    is_push_endpoint,
)
from openfinance.domain.shared import Money


def alert(kind: AlertKind, key: str) -> Alert:
    return Alert(
        kind, key, Severity.INFO, "Netflix ha subido", "De 10.00 a 12.00 EUR", date(2026, 11, 3),
        Money.of("2.00", "EUR"),
    )  # fmt: skip


def test_no_alerts_no_message() -> None:
    assert digest_message([]) is None


def test_one_alert_is_singular_and_names_no_merchant_or_amount() -> None:
    message = digest_message([alert(AlertKind.PRICE_RISE, "a")])
    assert message is not None
    assert message.title == "Tienes 1 aviso nuevo" and message.body == "1 subida de precio"
    assert "Netflix" not in message.body and "10.00" not in message.body


def test_several_are_grouped_by_kind() -> None:
    message = digest_message(
        [alert(AlertKind.FEE, "a"), alert(AlertKind.FEE, "b"), alert(AlertKind.DUPLICATE, "c")]
    )
    assert message is not None
    assert message.title == "Tienes 3 avisos nuevos"
    assert message.body == "1 posible duplicado, 2 comisiones"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/x",
        "https://updates.push.services.mozilla.com/wpush/v2/x",
        "https://web.push.apple.com/x",
        "https://wns2-par02p.notify.windows.com/w/?token=x",
    ],
)
def test_known_push_services(endpoint: str) -> None:
    assert is_push_endpoint(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "ftp://fcm.googleapis.com/x",
        "https://notfcm.googleapis.com.evil.org/x",
        "https://localhost/x",
    ],
)
def test_other_hosts_are_refused(endpoint: str) -> None:
    assert not is_push_endpoint(endpoint)


def test_a_subscription_needs_keys_and_a_known_service() -> None:
    with pytest.raises(NotificationError):
        PushSubscription("https://fcm.googleapis.com/x", "", "auth")
    with pytest.raises(NotificationError):
        PushSubscription("https://example.org/x", "key", "auth")
