"""OF-1402: sincronización de movimientos del banco por la tubería de importación."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from openfinance.application.bank import MIN_AUTO_INTERVAL, sync_all, sync_connection
from openfinance.domain.bank import RemoteBalance, RemoteTransaction
from openfinance.domain.shared import Money
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from tests.db.conftest import CSRF  # noqa: F401
from tests.db.test_bank_api import FakeAggregator, connect

TODAY = datetime.now(UTC).date()


def remote(entry, amount, days_ago=1, desc="Mercadona", currency="EUR"):
    return RemoteTransaction(
        entry, TODAY - timedelta(days=days_ago), Decimal(amount), currency, desc
    )


@pytest.fixture
def aggregator(app) -> FakeAggregator:
    from openfinance.api.deps import get_bank_aggregator

    fake = FakeAggregator()
    app.dependency_overrides[get_bank_aggregator] = lambda: fake
    return fake


def link(client, connection, account, uid="uid-1"):
    r = client.put(
        f"/api/v1/bank/connections/{connection['id']}/link",
        json={"remote_uid": uid, "account_id": str(account.id)},
    )
    assert r.status_code == 200, r.text
    return r.json()


def synced(client, connection):
    return client.post(f"/api/v1/bank/connections/{connection['id']}/sync")


def account_txns(session_factory, account):
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        return uow.transactions.for_account(account.household_id, account.id)


def run(session_factory, fake, household_id, connection_id, when, **kw):
    """Sincroniza como lo haría cron en otro momento."""
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        found = uow.bank.get(household_id, UUID(connection_id))
        assert found is not None
        return sync_connection(uow, fake, found, when, **kw)


def test_sync_saves_new_movements_with_their_provenance(as_raul, seed, aggregator, session_factory):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.raul_personal)
    aggregator.transactions_by_uid["uid-1"] = [
        remote("A1", "-12.50", 3, "Mercadona"),
        remote("A2", "1500.00", 2, "Nómina octubre"),
    ]
    r = synced(as_raul, connection)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 2
    assert body["links"][0]["error"] == ""
    assert body["connection"]["last_sync_at"] is not None
    new = [
        t
        for t in account_txns(session_factory, seed.raul_personal)
        if t.source.startswith("banco:")
    ]
    assert {(t.description, t.amount.amount) for t in new} == {
        ("Mercadona", Decimal("-12.50")),
        ("Nómina octubre", Decimal("1500.00")),
    }
    assert all(t.source == "banco:Bankinter" and t.bank_type == "PSD2" for t in new)
    # la sesión del agregador viaja con la petición, nunca por la API
    assert aggregator.requested[0][0] == "sess-secret-1"
    assert "sess-secret-1" not in r.text


def test_syncing_twice_does_not_duplicate(as_raul, seed, aggregator, session_factory):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("A1", "-5.00"), remote("A2", "-7.00")]
    before = len(account_txns(session_factory, seed.joint))
    first = synced(as_raul, connection).json()
    assert first["created"] == 2
    later = datetime.now(UTC) + timedelta(hours=1)
    report = run(session_factory, aggregator, seed.joint.household_id, connection["id"], later)
    assert report.created == 0
    assert report.links[0].duplicates == 2
    assert len(account_txns(session_factory, seed.joint)) == before + 2


def test_a_new_movement_arrives_on_the_next_sync(as_raul, seed, aggregator, session_factory):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("A1", "-5.00")]
    synced(as_raul, connection)
    aggregator.transactions_by_uid["uid-1"] = [remote("A1", "-5.00"), remote("A2", "-9.00", 0)]
    report = run(
        session_factory,
        aggregator,
        seed.joint.household_id,
        connection["id"],
        datetime.now(UTC) + timedelta(hours=1),
    )
    assert (report.created, report.links[0].duplicates) == (1, 1)


def test_the_window_starts_90_days_back_then_overlaps_a_week(
    as_raul, seed, aggregator, session_factory
):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.joint)
    synced(as_raul, connection)
    first_since = aggregator.requested[0][2]
    assert (TODAY - first_since).days == 90
    run(
        session_factory,
        aggregator,
        seed.joint.household_id,
        connection["id"],
        datetime.now(UTC) + timedelta(hours=1),
    )
    second_since = aggregator.requested[1][2]
    assert (TODAY - second_since).days == 7


def test_each_sync_is_an_import_batch_that_can_be_undone(
    as_raul, seed, aggregator, session_factory
):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("A1", "-5.00"), remote("A2", "-7.00")]
    synced(as_raul, connection)
    batches = as_raul.get("/api/v1/imports").json()
    bank_batch = next(b for b in batches if b["filename"].startswith("banco:"))
    assert bank_batch["created"] == 2
    undone = as_raul.post(f"/api/v1/imports/{bank_batch['id']}/undo")
    assert undone.status_code == 200
    assert undone.json()["voided"] == 2
    # y volver a sincronizar los recupera con su identificador, sin duplicar
    report = run(
        session_factory,
        aggregator,
        seed.joint.household_id,
        connection["id"],
        datetime.now(UTC) + timedelta(hours=1),
    )
    assert report.created == 2
    active = [
        t
        for t in account_txns(session_factory, seed.joint)
        if t.source.startswith("banco:") and not t.voided
    ]
    assert len(active) == 2


def test_other_currencies_are_skipped_and_counted(as_raul, seed, aggregator):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [
        remote("A1", "-5.00"),
        remote("A2", "-5.00", currency="USD"),
    ]
    body = synced(as_raul, connection).json()
    assert (body["created"], body["links"][0]["skipped"]) == (1, 1)


def test_a_bank_failure_changes_nothing_and_is_reported(as_raul, seed, aggregator, session_factory):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.joint)
    aggregator.fail_transactions = True
    before = len(account_txns(session_factory, seed.joint))
    body = synced(as_raul, connection).json()
    assert body["created"] == 0
    assert "limita las consultas" in body["links"][0]["error"]
    assert "limita las consultas" in body["connection"]["last_error"]
    assert body["connection"]["last_sync_at"] is None
    assert len(account_txns(session_factory, seed.joint)) == before
    # al recuperarse, el error se limpia
    aggregator.fail_transactions = False
    aggregator.transactions_by_uid["uid-1"] = [remote("A1", "-5.00")]
    ok = synced(as_raul, connection).json()
    assert ok["created"] == 1
    assert ok["connection"]["last_error"] == ""


def test_unlinked_accounts_are_not_fetched(as_raul, aggregator):
    connection = connect(as_raul, aggregator)
    body = synced(as_raul, connection).json()
    assert body["links"] == []
    assert aggregator.requested == []


def test_too_soon_for_a_manual_sync(as_raul, seed, aggregator):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.joint)
    synced(as_raul, connection)
    again = synced(as_raul, connection).json()
    assert "hace poco" in again["skipped_reason"]
    assert len(aggregator.requested) == 1


def test_only_the_owner_can_sync_and_personal_movements_stay_private(
    as_raul, as_elena, as_ana, seed, aggregator
):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.raul_personal)
    aggregator.transactions_by_uid["uid-1"] = [remote("A1", "-33.33", 1, "Gasolinera personal")]
    for other in (as_elena, as_ana):
        assert synced(other, connection).status_code == 404
    assert aggregator.requested == []
    assert synced(as_raul, connection).json()["created"] == 1
    # lo traído a una cuenta personal solo lo ve su titular
    seen_by_elena = as_elena.get("/api/v1/transactions", params={"limit": 200}).text
    assert "Gasolinera personal" not in seen_by_elena
    assert "Gasolinera personal" in as_raul.get("/api/v1/transactions", params={"limit": 200}).text


def test_the_bank_balance_is_kept_for_each_account(as_raul, seed, aggregator):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.joint)
    aggregator.balances["uid-1"] = RemoteBalance(Money.of("321.00", "EUR"), datetime.now(UTC))
    body = synced(as_raul, connection).json()
    assert body["connection"]["links"][0]["bank_balance"] == {
        "amount": "321.0000",
        "currency": "EUR",
    } or (body["connection"]["links"][0]["bank_balance"]["amount"].startswith("321"))


def test_revoked_and_pending_connections_do_not_sync(as_raul, seed, aggregator):
    started = as_raul.post("/api/v1/bank/connections", json={"aspsp": "Bankinter", "country": "ES"})
    pending = {"id": started.json()["connection_id"]}
    assert synced(as_raul, pending).status_code == 409
    connection = connect(as_raul, aggregator)
    as_raul.post(f"/api/v1/bank/connections/{connection['id']}/revoke")
    assert synced(as_raul, connection).status_code == 409


def test_an_expired_consent_stops_syncing(as_raul, seed, aggregator, session_factory):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.joint)
    future = datetime.now(UTC) + timedelta(days=400)
    report = run(session_factory, aggregator, seed.joint.household_id, connection["id"], future)
    assert "caducado" in report.skipped_reason
    assert aggregator.requested == []
    assert as_raul.get("/api/v1/bank").json()["connections"][0]["status"] == "expired"


def test_sync_all_covers_every_household_and_respects_the_daily_limit(
    as_raul, as_ana, seed, aggregator, session_factory
):
    mine = connect(as_raul, aggregator)
    link(as_raul, mine, seed.joint)
    theirs = connect(as_ana, aggregator, "Revolut")
    link(as_ana, theirs, seed.other_joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("A1", "-5.00")]
    now = datetime.now(UTC)
    with session_factory() as s:
        reports = sync_all(SqlUnitOfWork(s), aggregator, now)
    assert len(reports) == 2
    assert sum(r.created for r in reports) == 2
    with session_factory() as s:
        soon = sync_all(SqlUnitOfWork(s), aggregator, now + timedelta(hours=1))
    assert all("hace poco" in r.skipped_reason for r in soon)
    with session_factory() as s:
        later = sync_all(
            SqlUnitOfWork(s), aggregator, now + MIN_AUTO_INTERVAL + timedelta(minutes=1)
        )
    assert all(not r.skipped_reason for r in later)


def test_one_failing_connection_does_not_stop_the_others(
    as_raul, as_ana, seed, aggregator, session_factory
):
    mine = connect(as_raul, aggregator)
    link(as_raul, mine, seed.joint)
    theirs = connect(as_ana, aggregator, "Revolut")
    link(as_ana, theirs, seed.other_joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("A1", "-5.00")]
    # el agregador falla solo para la primera cuenta consultada
    original = aggregator.transactions
    calls = {"n": 0}

    def flaky(session_id, uid, since):
        calls["n"] += 1
        if calls["n"] == 1:
            aggregator.fail_transactions = True
        else:
            aggregator.fail_transactions = False
        return original(session_id, uid, since)

    aggregator.transactions = flaky  # type: ignore[method-assign]
    with session_factory() as s:
        reports = sync_all(SqlUnitOfWork(s), aggregator, datetime.now(UTC))
    assert sorted(r.created for r in reports) == [0, 1]


def test_renewing_the_consent_does_not_bring_the_history_again(
    as_raul, seed, aggregator, session_factory
):
    old = connect(as_raul, aggregator)
    link(as_raul, old, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("A1", "-5.00"), remote("A2", "-7.00")]
    assert synced(as_raul, old).json()["created"] == 2
    as_raul.post(f"/api/v1/bank/connections/{old['id']}/revoke")
    # otra sesión y otros ids de cuenta en el agregador, pero el banco repite sus referencias
    renewed = connect(as_raul, aggregator)
    link(as_raul, renewed, seed.joint)
    again = synced(as_raul, renewed).json()
    assert (again["created"], again["links"][0]["duplicates"]) == (0, 2)


def test_sync_refuses_an_account_that_became_invisible(as_raul, seed, aggregator, session_factory):
    connection = connect(as_raul, aggregator)
    link(as_raul, connection, seed.raul_personal)
    aggregator.transactions_by_uid["uid-1"] = [remote("A1", "-5.00")]
    # la cuenta pasa a ser de Elena: Raúl ya no la ve y su conexión no puede escribir en ella
    with session_factory() as s:
        from sqlalchemy import update

        from openfinance.infrastructure.db.models import AccountRow

        s.execute(
            update(AccountRow)
            .where(AccountRow.id == seed.raul_personal.id)
            .values(owner_id=seed.elena.id)
        )
        s.commit()
    body = synced(as_raul, connection).json()
    assert body["created"] == 0
    assert "ya no está disponible" in body["links"][0]["error"]
    assert aggregator.requested == []
