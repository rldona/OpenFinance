"""OF-1302: dispositivos, preferencias y envío de notificaciones push."""

from datetime import timedelta

import pytest

from openfinance.application.notifications import send_pending
from openfinance.domain.notifications import PushMessage, PushSubscription, SendResult
from openfinance.infrastructure.config import Settings, get_settings
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from openfinance.infrastructure.time import local_today, utc_now

TODAY = local_today()
FCM = "https://fcm.googleapis.com/fcm/send/abc123"
MOZILLA = "https://updates.push.services.mozilla.com/wpush/v2/xyz"


class FakeSender:
    def __init__(self, enabled: bool = True, result: SendResult = SendResult.SENT) -> None:
        self._enabled = enabled
        self.result = result
        self.sent: list[tuple[PushSubscription, PushMessage]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def send(self, subscription: PushSubscription, message: PushMessage) -> SendResult:
        self.sent.append((subscription, message))
        return self.result


def subscribe(client, endpoint=FCM):
    return client.post(
        "/api/v1/notifications/subscriptions",
        json={"endpoint": endpoint, "keys": {"p256dh": "BPubKey", "auth": "AuthSecret"}},
    )


def alerts_only(client):
    """Sin el resumen semanal, para contar solo los mensajes de avisos."""
    client.put(
        "/api/v1/notifications/preferences",
        json={
            "kinds": [
                "late_payment",
                "low_balance",
                "budget_over",
                "duplicate",
                "price_rise",
                "fee",
            ],
            "weekly": False,
        },
    )


def fee(client, seed, description="Comisión de mantenimiento"):
    r = client.post(
        "/api/v1/transactions",
        json={
            "booked_on": (TODAY - timedelta(days=1)).isoformat(),
            "description": description,
            "amount": "2.00",
            "kind": "expense",
            "account_id": str(seed.joint.id),
        },
    )
    assert r.status_code == 201, r.text


def run(session_factory, sender):
    with session_factory() as session:
        return send_pending(SqlUnitOfWork(session), sender, TODAY, utc_now())


class TestStatusAndPreferences:
    def test_without_keys_it_says_it_is_off(self, as_raul) -> None:
        body = as_raul.get("/api/v1/notifications").json()
        assert body["configured"] is False and body["public_key"] is None
        assert body["devices"] == 0 and body["weekly"] is True
        assert sorted(body["kinds"]) == sorted(
            ["late_payment", "low_balance", "budget_over", "duplicate", "price_rise", "fee"]
        )

    def test_with_keys_it_gives_the_public_key_and_never_the_private_one(
        self, app, as_raul
    ) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(
            vapid_public_key="PUBLIC", vapid_private_key="SECRET", vapid_subject="mailto:a@b.es"
        )
        r = as_raul.get("/api/v1/notifications")
        assert r.json()["configured"] is True and r.json()["public_key"] == "PUBLIC"
        assert "SECRET" not in r.text

    def test_preferences_are_per_person(self, as_raul, as_elena) -> None:
        r = as_raul.put(
            "/api/v1/notifications/preferences", json={"kinds": ["low_balance"], "weekly": False}
        )
        assert r.json()["kinds"] == ["low_balance"] and r.json()["weekly"] is False
        assert as_raul.get("/api/v1/notifications").json()["kinds"] == ["low_balance"]
        assert len(as_elena.get("/api/v1/notifications").json()["kinds"]) == 6

    def test_unknown_kinds_are_refused(self, as_raul) -> None:
        r = as_raul.put("/api/v1/notifications/preferences", json={"kinds": ["x"], "weekly": True})
        assert r.status_code == 422


class TestDevices:
    def test_subscribe_counts_and_removes(self, as_raul) -> None:
        assert subscribe(as_raul).status_code == 204
        assert subscribe(as_raul).status_code == 204  # repetirlo no duplica
        assert as_raul.get("/api/v1/notifications").json()["devices"] == 1
        r = as_raul.post("/api/v1/notifications/subscriptions/remove", json={"endpoint": FCM})
        assert r.status_code == 204
        assert as_raul.get("/api/v1/notifications").json()["devices"] == 0

    @pytest.mark.parametrize(
        "endpoint",
        [
            "http://fcm.googleapis.com/x",
            "https://evil.example.org/fcm.googleapis.com",
            "https://fcm.googleapis.com.evil.org/x",
            "https://user:pw@fcm.googleapis.com/x",
            "https://fcm.googleapis.com:8443/x",
            "https://127.0.0.1/x",
            "https://169.254.169.254/latest/meta-data",
        ],
    )
    def test_only_push_services_are_accepted(self, as_raul, endpoint) -> None:
        assert subscribe(as_raul, endpoint).status_code == 422

    def test_a_person_cannot_remove_anothers_device(self, as_raul, as_elena) -> None:
        subscribe(as_elena)
        as_raul.post("/api/v1/notifications/subscriptions/remove", json={"endpoint": FCM})
        assert as_elena.get("/api/v1/notifications").json()["devices"] == 1

    def test_the_device_belongs_to_whoever_logged_in_on_it_last(self, as_raul, as_elena) -> None:
        subscribe(as_raul)
        subscribe(as_elena)
        assert as_raul.get("/api/v1/notifications").json()["devices"] == 0
        assert as_elena.get("/api/v1/notifications").json()["devices"] == 1

    def test_there_is_a_limit_of_devices(self, as_raul) -> None:
        for i in range(10):
            assert subscribe(as_raul, f"https://fcm.googleapis.com/{i}").status_code == 204
        assert subscribe(as_raul, "https://fcm.googleapis.com/eleven").status_code == 409
        assert subscribe(as_raul, "https://fcm.googleapis.com/3").status_code == 204

    def test_requires_login_and_the_csrf_header(self, client, as_raul) -> None:
        assert client.get("/api/v1/notifications").status_code == 401
        as_raul.headers.pop("X-Requested-With", None)
        assert subscribe(as_raul).status_code == 403


class TestSending:
    def test_sends_one_digest_without_amounts_or_merchants(
        self, as_raul, seed, session_factory
    ) -> None:
        subscribe(as_raul)
        alerts_only(as_raul)
        fee(as_raul, seed, "Comisión secreta Banco XYZ")
        sender = FakeSender()
        report = run(session_factory, sender)
        assert (report.sent, report.people) == (1, 1)
        ((_, message),) = sender.sent
        assert "comisión" in message.body
        text = f"{message.title} {message.body} {message.url}"
        assert "2.00" not in text and "XYZ" not in text and "secreta" not in text
        assert message.title.startswith("Tienes ")

    def test_running_it_again_sends_nothing_new(self, as_raul, seed, session_factory) -> None:
        subscribe(as_raul)
        fee(as_raul, seed)
        run(session_factory, FakeSender())
        again = FakeSender()
        assert run(session_factory, again).sent == 0 and again.sent == []

    def test_a_new_alert_is_sent_alone(self, as_raul, seed, session_factory) -> None:
        subscribe(as_raul)
        fee(as_raul, seed)
        run(session_factory, FakeSender())
        fee(as_raul, seed, "Comisión nueva")
        sender = FakeSender()
        run(session_factory, sender)
        assert len(sender.sent) == 1 and sender.sent[0][1].title == "Tienes 1 aviso nuevo"

    def test_a_failed_delivery_is_retried_next_time(self, as_raul, seed, session_factory) -> None:
        subscribe(as_raul)
        alerts_only(as_raul)
        fee(as_raul, seed)
        failing = FakeSender(result=SendResult.FAILED)
        assert run(session_factory, failing).failed == 1
        ok = FakeSender()
        assert run(session_factory, ok).sent == 1

    def test_a_gone_device_is_removed(self, as_raul, seed, session_factory) -> None:
        subscribe(as_raul)
        fee(as_raul, seed)
        report = run(session_factory, FakeSender(result=SendResult.GONE))
        assert report.removed == 1
        assert as_raul.get("/api/v1/notifications").json()["devices"] == 0

    def test_muted_kinds_are_not_sent(self, as_raul, seed, session_factory) -> None:
        subscribe(as_raul)
        as_raul.put(
            "/api/v1/notifications/preferences", json={"kinds": ["duplicate"], "weekly": True}
        )
        fee(as_raul, seed)
        sender = FakeSender()
        run(session_factory, sender)
        assert all("comisión" not in m.body for _, m in sender.sent)

    def test_without_a_device_nothing_is_sent(self, as_raul, seed, session_factory) -> None:
        fee(as_raul, seed)
        sender = FakeSender()
        assert run(session_factory, sender).people == 0 and sender.sent == []

    def test_when_push_is_off_nothing_is_sent(self, as_raul, seed, session_factory) -> None:
        subscribe(as_raul)
        fee(as_raul, seed)
        sender = FakeSender(enabled=False)
        assert run(session_factory, sender).sent == 0 and sender.sent == []

    def test_a_personal_alert_never_reaches_the_other_persons_phone(
        self, as_raul, as_elena, seed, session_factory
    ) -> None:
        subscribe(as_raul, FCM)
        subscribe(as_elena, MOZILLA)
        r = as_elena.post(
            "/api/v1/transactions",
            json={
                "booked_on": (TODAY - timedelta(days=1)).isoformat(),
                "description": "Comisión privada de Elena",
                "amount": "9.00",
                "kind": "expense",
                "account_id": str(seed.elena_personal.id),
            },
        )
        assert r.status_code == 201, r.text
        sender = FakeSender()
        run(session_factory, sender)
        targets = {s.endpoint: m for s, m in sender.sent if "comisión" in m.body}
        assert MOZILLA in targets and FCM not in targets
