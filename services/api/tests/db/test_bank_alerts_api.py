"""OF-1403: aviso de consentimiento por caducar y caducado, solo para su titular."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from openfinance.api.deps import get_bank_aggregator
from openfinance.domain.alerts import AlertKind, consents
from openfinance.domain.bank import BankConnection, ConsentStatus
from tests.db.test_bank_api import FakeAggregator, connect

TODAY = datetime.now(UTC).date()


@pytest.fixture
def aggregator(app) -> FakeAggregator:
    fake = FakeAggregator()
    app.dependency_overrides[get_bank_aggregator] = lambda: fake
    return fake


def consent_alerts(client):
    return [a for a in client.get("/api/v1/alerts").json() if a["kind"] == "consent"]


def test_no_alert_while_the_consent_is_far_from_expiring(as_raul, aggregator):
    aggregator.valid_days = 120
    connect(as_raul, aggregator)
    assert consent_alerts(as_raul) == []


def test_it_warns_two_weeks_before_and_only_its_owner(as_raul, as_elena, as_ana, aggregator):
    aggregator.valid_days = 10
    connect(as_raul, aggregator)
    [alert] = consent_alerts(as_raul)
    assert alert["severity"] == "warning"
    assert "Bankinter" in alert["title"] and "caduca" in alert["title"]
    assert alert["account_id"] is None and alert["amount"] is None
    assert alert["key"].startswith("consent:")
    # Elena, de su mismo hogar, y Ana, de otro, no la ven
    assert consent_alerts(as_elena) == []
    assert consent_alerts(as_ana) == []
    # y no pueden descartarla (404)
    for other in (as_elena, as_ana):
        r = other.post("/api/v1/alerts/dismiss", json={"key": alert["key"]})
        assert r.status_code == 404


def test_the_owner_can_dismiss_it(as_raul, aggregator):
    aggregator.valid_days = 5
    connect(as_raul, aggregator)
    [alert] = consent_alerts(as_raul)
    assert as_raul.post("/api/v1/alerts/dismiss", json={"key": alert["key"]}).status_code == 204
    assert consent_alerts(as_raul) == []


def test_a_revoked_connection_does_not_warn(as_raul, aggregator):
    aggregator.valid_days = 3
    connection = connect(as_raul, aggregator)
    as_raul.post(f"/api/v1/bank/connections/{connection['id']}/revoke")
    assert consent_alerts(as_raul) == []


def test_it_can_be_chosen_as_a_notification_kind(as_raul):
    r = as_raul.put(
        "/api/v1/notifications/preferences", json={"kinds": ["consent"], "weekly": False}
    )
    assert r.status_code == 200
    assert r.json()["kinds"] == ["consent"]


# --- reglas puras ----------------------------------------------------------------------------


def connection(status, valid_in_days, aspsp="Bankinter"):
    return BankConnection(
        id=uuid4(),
        household_id=uuid4(),
        owner_id=uuid4(),
        aspsp=aspsp,
        country="ES",
        status=status,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime.combine(
            TODAY + timedelta(days=valid_in_days), datetime.min.time(), UTC
        ),
        links=(),
    )


def test_expiry_window_boundaries():
    assert consents([connection(ConsentStatus.ACTIVE, 15)], TODAY) == []
    [soon] = consents([connection(ConsentStatus.ACTIVE, 14)], TODAY)
    assert soon.kind is AlertKind.CONSENT and "caduca el" in soon.title
    [today] = consents([connection(ConsentStatus.ACTIVE, 0)], TODAY)
    assert "caduca hoy" in today.title


def test_an_expired_consent_warns_for_a_month_then_stops():
    [recent] = consents([connection(ConsentStatus.ACTIVE, -1)], TODAY)
    assert recent.severity.value == "critical" and recent.key.startswith("consent_expired:")
    assert len(consents([connection(ConsentStatus.EXPIRED, -30)], TODAY)) == 1
    assert consents([connection(ConsentStatus.EXPIRED, -31)], TODAY) == []


def test_a_renewed_connection_silences_the_expired_one():
    old = connection(ConsentStatus.EXPIRED, -3)
    renewed = connection(ConsentStatus.ACTIVE, 120)
    assert consents([old, renewed], TODAY) == []
    other_bank = connection(ConsentStatus.ACTIVE, 120, aspsp="Revolut")
    assert len(consents([old, other_bank], TODAY)) == 1


def test_pending_and_revoked_never_warn():
    assert (
        consents(
            [connection(ConsentStatus.PENDING, 3), connection(ConsentStatus.REVOKED, 3)], TODAY
        )
        == []
    )
