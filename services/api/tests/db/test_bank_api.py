"""OF-1401: consentimiento con el banco, cuentas enlazadas y revocación (ADR-0024)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from openfinance.api.deps import get_bank_aggregator
from openfinance.application.errors import AggregatorError
from openfinance.domain.bank import BankAccountRef, RemoteBalance, RemoteTransaction
from tests.db.conftest import CSRF


class FakeAggregator:
    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self.started: list[tuple[str, str, str, datetime]] = []
        self.revoked: list[str] = []
        self.fail_start = False
        self.fail_authorize = False
        self.fail_revoke = False
        self.accounts = [
            BankAccountRef("uid-1", "1234", "Cuenta corriente", "EUR"),
            BankAccountRef("uid-2", "9876", "Cuenta de ahorro", "EUR"),
        ]
        self.transactions_by_uid: dict[str, list[RemoteTransaction]] = {}
        self.balances: dict[str, RemoteBalance] = {}
        self.fail_transactions = False
        self.valid_days = 120
        self.requested: list[tuple[str, str, object]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def banks(self, country: str) -> list[str]:
        return ["Bankinter", "Revolut"]

    def start(self, aspsp: str, country: str, state: str, valid_until: datetime) -> str:
        if self.fail_start:
            raise AggregatorError("El banco no pudo atender la petición")
        self.started.append((aspsp, country, state, valid_until))
        return f"https://bank.example/auth?s={state[:6]}"

    def authorize(self, code: str):
        if self.fail_authorize:
            raise AggregatorError("El banco rechazó la petición")
        return (
            "sess-secret-1",
            list(self.accounts),
            datetime.now(UTC) + timedelta(days=self.valid_days),
        )

    def transactions(self, session_id: str, remote_uid: str, since):
        self.requested.append((session_id, remote_uid, since))
        if self.fail_transactions:
            raise AggregatorError("El banco limita las consultas; se reintentará más tarde")
        return list(self.transactions_by_uid.get(remote_uid, []))

    def balance(self, session_id: str, remote_uid: str):
        return self.balances.get(remote_uid)

    def revoke(self, session_id: str) -> None:
        if self.fail_revoke:
            raise AggregatorError("El banco no pudo atender la petición")
        self.revoked.append(session_id)


@pytest.fixture
def aggregator(app) -> FakeAggregator:
    fake = FakeAggregator()
    app.dependency_overrides[get_bank_aggregator] = lambda: fake
    return fake


def connect(client: TestClient, fake: FakeAggregator, bank: str = "Bankinter") -> dict:
    started = client.post("/api/v1/bank/connections", json={"aspsp": bank, "country": "es"})
    assert started.status_code == 201, started.text
    state = fake.started[-1][2]
    done = client.post("/api/v1/bank/connections/complete", json={"state": state, "code": "c0de"})
    assert done.status_code == 200, done.text
    return done.json()


def test_start_returns_the_bank_url_and_stores_a_pending_connection(as_raul, aggregator):
    r = as_raul.post("/api/v1/bank/connections", json={"aspsp": "Bankinter", "country": "es"})
    assert r.status_code == 201
    assert r.json()["url"].startswith("https://bank.example/auth")
    aspsp, country, state, valid_until = aggregator.started[0]
    assert (aspsp, country) == ("Bankinter", "ES")
    assert len(state) >= 40
    assert valid_until > datetime.now(UTC) + timedelta(days=170)
    listed = as_raul.get("/api/v1/bank").json()
    assert [c["status"] for c in listed["connections"]] == ["pending"]
    # El state no sale por la API: solo lo conoce quien vuelve del banco.
    assert state not in as_raul.get("/api/v1/bank").text


def test_complete_activates_and_lists_accounts_without_credentials(as_raul, aggregator):
    connection = connect(as_raul, aggregator)
    assert connection["status"] == "active"
    assert [(link["name"], link["iban_tail"]) for link in connection["links"]] == [
        ("Cuenta corriente", "1234"),
        ("Cuenta de ahorro", "9876"),
    ]
    assert all(link["account_id"] is None for link in connection["links"])
    text = as_raul.get("/api/v1/bank").text
    assert "sess-secret-1" not in text
    assert "session" not in text


def test_the_return_state_is_single_use(as_raul, aggregator):
    connect(as_raul, aggregator)
    state = aggregator.started[0][2]
    again = as_raul.post("/api/v1/bank/connections/complete", json={"state": state, "code": "x"})
    assert again.status_code == 404


def test_someone_else_cannot_complete_my_connection(app, as_raul, as_elena, as_ana, aggregator):
    as_raul.post("/api/v1/bank/connections", json={"aspsp": "Bankinter", "country": "ES"})
    state = aggregator.started[0][2]
    for other in (as_elena, as_ana):
        r = other.post("/api/v1/bank/connections/complete", json={"state": state, "code": "x"})
        assert r.status_code == 404
    # y la conexión sigue pendiente para su dueño
    done = as_raul.post("/api/v1/bank/connections/complete", json={"state": state, "code": "x"})
    assert done.status_code == 200


def test_connections_are_private_to_their_owner(as_raul, as_elena, as_ana, aggregator):
    connection = connect(as_raul, aggregator)
    for other in (as_elena, as_ana):
        assert other.get("/api/v1/bank").json()["connections"] == []
        cid = connection["id"]
        link = other.put(
            f"/api/v1/bank/connections/{cid}/link",
            json={"remote_uid": "uid-1", "account_id": None},
        )
        assert link.status_code == 404
        assert other.post(f"/api/v1/bank/connections/{cid}/revoke").status_code == 404
    assert aggregator.revoked == []


def test_link_to_an_account_i_can_see(as_raul, seed, aggregator):
    connection = connect(as_raul, aggregator)
    cid = connection["id"]
    for account in (seed.raul_personal, seed.joint):
        r = as_raul.put(
            f"/api/v1/bank/connections/{cid}/link",
            json={"remote_uid": "uid-1", "account_id": str(account.id)},
        )
        assert r.status_code == 200, r.text
        assert r.json()["links"][0]["account_id"] == str(account.id)


def test_cannot_link_someone_elses_personal_account_or_another_household(as_raul, seed, aggregator):
    cid = connect(as_raul, aggregator)["id"]
    for account in (seed.elena_personal, seed.other_joint):
        r = as_raul.put(
            f"/api/v1/bank/connections/{cid}/link",
            json={"remote_uid": "uid-1", "account_id": str(account.id)},
        )
        assert r.status_code == 404


def test_an_account_receives_from_one_bank_account_only(as_raul, seed, aggregator):
    cid = connect(as_raul, aggregator)["id"]
    body = {"remote_uid": "uid-1", "account_id": str(seed.joint.id)}
    assert as_raul.put(f"/api/v1/bank/connections/{cid}/link", json=body).status_code == 200
    second = as_raul.put(
        f"/api/v1/bank/connections/{cid}/link",
        json={"remote_uid": "uid-2", "account_id": str(seed.joint.id)},
    )
    assert second.status_code == 422
    # ni desde otra conexión
    other = connect(as_raul, aggregator, "Revolut")
    third = as_raul.put(
        f"/api/v1/bank/connections/{other['id']}/link",
        json={"remote_uid": "uid-1", "account_id": str(seed.joint.id)},
    )
    assert third.status_code == 422


def test_unlink_and_unknown_remote_account(as_raul, seed, aggregator):
    cid = connect(as_raul, aggregator)["id"]
    url = f"/api/v1/bank/connections/{cid}/link"
    as_raul.put(url, json={"remote_uid": "uid-1", "account_id": str(seed.joint.id)})
    cleared = as_raul.put(url, json={"remote_uid": "uid-1", "account_id": None})
    assert cleared.json()["links"][0]["account_id"] is None
    assert as_raul.put(url, json={"remote_uid": "nope", "account_id": None}).status_code == 404


def test_revoke_closes_the_session_and_stops_linking(as_raul, seed, aggregator):
    cid = connect(as_raul, aggregator)["id"]
    r = as_raul.post(f"/api/v1/bank/connections/{cid}/revoke")
    assert r.status_code == 200
    assert r.json()["closed_at_bank"] is True
    assert r.json()["connection"]["status"] == "revoked"
    assert aggregator.revoked == ["sess-secret-1"]
    link = as_raul.put(
        f"/api/v1/bank/connections/{cid}/link",
        json={"remote_uid": "uid-1", "account_id": str(seed.joint.id)},
    )
    assert link.status_code == 422


def test_revoke_still_revokes_when_the_bank_fails(as_raul, aggregator):
    cid = connect(as_raul, aggregator)["id"]
    aggregator.fail_revoke = True
    r = as_raul.post(f"/api/v1/bank/connections/{cid}/revoke")
    assert r.status_code == 200
    assert r.json()["closed_at_bank"] is False
    assert r.json()["connection"]["status"] == "revoked"


def test_a_failed_authorization_cannot_be_retried_with_the_same_state(as_raul, aggregator):
    as_raul.post("/api/v1/bank/connections", json={"aspsp": "Bankinter", "country": "ES"})
    state = aggregator.started[0][2]
    aggregator.fail_authorize = True
    failed = as_raul.post("/api/v1/bank/connections/complete", json={"state": state, "code": "x"})
    assert failed.status_code == 502
    aggregator.fail_authorize = False
    retry = as_raul.post("/api/v1/bank/connections/complete", json={"state": state, "code": "x"})
    assert retry.status_code == 404
    assert as_raul.get("/api/v1/bank").json()["connections"][0]["status"] == "revoked"


def test_an_aggregator_error_on_start_stores_nothing(as_raul, aggregator):
    aggregator.fail_start = True
    r = as_raul.post("/api/v1/bank/connections", json={"aspsp": "Bankinter", "country": "ES"})
    assert r.status_code == 502
    assert as_raul.get("/api/v1/bank").json()["connections"] == []


def test_without_configuration_the_feature_is_off(app, as_raul):
    app.dependency_overrides[get_bank_aggregator] = lambda: FakeAggregator(enabled=False)
    assert as_raul.get("/api/v1/bank").json() == {"configured": False, "connections": []}
    r = as_raul.post("/api/v1/bank/connections", json={"aspsp": "Bankinter", "country": "ES"})
    assert r.status_code == 422
    assert as_raul.get("/api/v1/bank/banks", params={"country": "ES"}).status_code == 422


def test_bank_names_and_input_validation(as_raul, aggregator):
    assert as_raul.get("/api/v1/bank/banks", params={"country": "es"}).json() == [
        "Bankinter",
        "Revolut",
    ]
    for body in ({"aspsp": "  ", "country": "ES"}, {"aspsp": "Bankinter", "country": "E1"}):
        assert as_raul.post("/api/v1/bank/connections", json=body).status_code == 422


def test_too_many_pending_connections(as_raul, aggregator):
    for _ in range(5):
        assert (
            as_raul.post(
                "/api/v1/bank/connections", json={"aspsp": "Bankinter", "country": "ES"}
            ).status_code
            == 201
        )
    sixth = as_raul.post("/api/v1/bank/connections", json={"aspsp": "Bankinter", "country": "ES"})
    assert sixth.status_code == 422


def test_requires_a_session_and_the_csrf_header(app, aggregator, seed, as_raul):
    anonymous = TestClient(app, headers=CSRF)
    assert anonymous.get("/api/v1/bank").status_code == 401
    assert anonymous.post("/api/v1/bank/connections", json={}).status_code == 401
    no_header = TestClient(app, cookies=as_raul.cookies)
    body = {"aspsp": "Bankinter", "country": "ES"}
    assert no_header.post("/api/v1/bank/connections", json=body).status_code == 403
