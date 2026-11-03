"""OF-1404: conciliación automática con lo ya anotado y saldo del banco."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from openfinance.api.deps import get_bank_aggregator
from openfinance.domain.bank import RemoteBalance, RemoteTransaction, reconcile_candidate
from openfinance.domain.imports import ImportedRow
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from tests.db.test_bank_api import FakeAggregator, connect
from tests.db.test_bank_sync_api import account_txns, link, run, synced

NOW = datetime.now(UTC)
TODAY = NOW.date()


@pytest.fixture
def aggregator(app) -> FakeAggregator:
    fake = FakeAggregator()
    app.dependency_overrides[get_bank_aggregator] = lambda: fake
    return fake


def remote(entry, amount, days_ago=1, desc="Mercadona"):
    return RemoteTransaction(entry, TODAY - timedelta(days=days_ago), Decimal(amount), "EUR", desc)


def add_manual(session_factory, account, amount, days_ago, desc="Super", **extra):
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        when = datetime.combine(TODAY - timedelta(days=days_ago), datetime.min.time()).replace(
            hour=12
        )
        t = Transaction(
            id=uuid4(),
            household_id=account.household_id,
            account_id=account.id,
            booked_at=when,
            value_date=when.date(),
            description=desc,
            amount=Money.of(amount, "EUR"),
            kind=TransactionKind.EXPENSE,
            **extra,
        )
        uow.transactions.add(t)
        uow.commit()
        return t


def active_bank_rows(session_factory, account):
    return [t for t in account_txns(session_factory, account) if t.source.startswith("banco:")]


def setup_link(client, aggregator, account):
    connection = connect(client, aggregator)
    link(client, connection, account)
    return connection


def test_a_manual_entry_with_the_same_amount_is_reconciled_not_duplicated(
    as_raul, seed, aggregator, session_factory
):
    manual = add_manual(session_factory, seed.joint, "-42.00", 3)
    connection = setup_link(as_raul, aggregator, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("B1", "-42.00", 2, "MERCADONA 0123")]
    body = synced(as_raul, connection).json()
    assert (body["created"], body["links"][0]["reconciled"]) == (0, 1)
    assert active_bank_rows(session_factory, seed.joint) == []
    reconciled = next(t for t in account_txns(session_factory, seed.joint) if t.id == manual.id)
    assert reconciled.bank_ref is not None
    assert reconciled.description == "Super"  # lo anotado no se reescribe
    assert as_raul.get("/api/v1/imports").json() == []  # y no hay lote vacío


def test_reconciling_is_idempotent(as_raul, seed, aggregator, session_factory):
    add_manual(session_factory, seed.joint, "-42.00", 3)
    connection = setup_link(as_raul, aggregator, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("B1", "-42.00", 2)]
    synced(as_raul, connection)
    count = len(account_txns(session_factory, seed.joint))
    later = NOW + timedelta(hours=1)
    again = run(session_factory, aggregator, seed.joint.household_id, connection["id"], later)
    assert (again.created, again.links[0].reconciled, again.links[0].duplicates) == (0, 0, 1)
    assert len(account_txns(session_factory, seed.joint)) == count


def test_different_amount_or_too_far_apart_creates_a_new_movement(
    as_raul, seed, aggregator, session_factory
):
    add_manual(session_factory, seed.joint, "-42.00", 8)
    add_manual(session_factory, seed.joint, "-41.99", 2)
    connection = setup_link(as_raul, aggregator, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("B1", "-42.00", 2)]
    body = synced(as_raul, connection).json()
    assert (body["created"], body["links"][0]["reconciled"]) == (1, 0)


def test_with_several_candidates_it_does_not_guess(as_raul, seed, aggregator, session_factory):
    add_manual(session_factory, seed.joint, "-10.00", 2, "Café A")
    add_manual(session_factory, seed.joint, "-10.00", 3, "Café B")
    connection = setup_link(as_raul, aggregator, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("B1", "-10.00", 2)]
    body = synced(as_raul, connection).json()
    assert (body["created"], body["links"][0]["reconciled"]) == (1, 0)


def test_one_manual_entry_reconciles_only_one_bank_row(as_raul, seed, aggregator, session_factory):
    add_manual(session_factory, seed.joint, "-10.00", 2)
    connection = setup_link(as_raul, aggregator, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("B1", "-10.00", 2), remote("B2", "-10.00", 2)]
    body = synced(as_raul, connection).json()
    assert (body["created"], body["links"][0]["reconciled"]) == (1, 1)


def test_a_voided_manual_entry_is_not_a_candidate(as_raul, seed, aggregator, session_factory):
    add_manual(session_factory, seed.joint, "-10.00", 2, voided=True)
    connection = setup_link(as_raul, aggregator, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("B1", "-10.00", 2)]
    body = synced(as_raul, connection).json()
    assert (body["created"], body["links"][0]["reconciled"]) == (1, 0)


def test_reconciling_an_imported_row_keeps_its_own_fingerprint(
    as_raul, seed, aggregator, session_factory
):
    """Reimportar el mismo extracto después de conciliar no puede duplicar el movimiento."""
    add_manual(
        session_factory,
        seed.joint,
        "-42.00",
        3,
        source="import:extracto.csv",
        fingerprint="csv-fingerprint",
    )
    connection = setup_link(as_raul, aggregator, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [remote("B1", "-42.00", 2)]
    assert synced(as_raul, connection).json()["links"][0]["reconciled"] == 1
    with session_factory() as s:
        found = SqlUnitOfWork(s).transactions.existing_fingerprints(
            seed.joint.household_id, seed.joint.id, ["csv-fingerprint"]
        )
    assert found == {"csv-fingerprint"}


def test_undoing_a_sync_leaves_reconciled_movements_alone(
    as_raul, seed, aggregator, session_factory
):
    manual = add_manual(session_factory, seed.joint, "-42.00", 3)
    connection = setup_link(as_raul, aggregator, seed.joint)
    aggregator.transactions_by_uid["uid-1"] = [
        remote("B1", "-42.00", 2),
        remote("B2", "-5.00", 1, "Panadería"),
    ]
    synced(as_raul, connection)
    batch = next(
        b for b in as_raul.get("/api/v1/imports").json() if b["filename"].startswith("banco:")
    )
    assert batch["created"] == 1
    as_raul.post(f"/api/v1/imports/{batch['id']}/undo")
    survivors = {t.id for t in account_txns(session_factory, seed.joint) if not t.voided}
    assert manual.id in survivors


def test_the_balance_difference_is_kept_and_does_not_change_anything(
    as_raul, seed, aggregator, session_factory
):
    connection = setup_link(as_raul, aggregator, seed.joint)
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        mine = uow.accounts.for_household(seed.joint.household_id)
        joint = next(a for a in mine if a.id == seed.joint.id)
        expected = joint.opening_balance + Money.of(
            uow.transactions.balances(joint.household_id, [joint.id]).get(joint.id, 0), "EUR"
        )
    aggregator.balances["uid-1"] = RemoteBalance(expected + Money.of("12.50", "EUR"), NOW)
    body = synced(as_raul, connection).json()
    bank_link = body["connection"]["links"][0]
    assert Decimal(bank_link["balance_difference"]["amount"]) == Decimal("12.50")
    assert bank_link["balance_difference"]["currency"] == "EUR"
    # coincide → diferencia cero
    aggregator.balances["uid-1"] = RemoteBalance(expected, NOW)
    report = run(
        session_factory,
        aggregator,
        seed.joint.household_id,
        connection["id"],
        NOW + timedelta(hours=1),
    )
    assert report.connection.links[0].balance_difference == Money.of("0", "EUR")


# --- regla pura ------------------------------------------------------------------------------


def row(amount, days_ago):
    when = datetime.combine(TODAY - timedelta(days=days_ago), datetime.min.time())
    return ImportedRow(
        when, when.date(), "x", Money.of(amount, "EUR"), "PSD2", TransactionKind.EXPENSE, "fp"
    )


def tx(amount, days_ago, **kw):
    when = datetime.combine(TODAY - timedelta(days=days_ago), datetime.min.time())
    return Transaction(
        id=uuid4(),
        household_id=uuid4(),
        account_id=uuid4(),
        booked_at=when,
        value_date=when.date(),
        description="x",
        amount=Money.of(amount, "EUR"),
        kind=TransactionKind.EXPENSE,
        **kw,
    )


def test_candidate_window_is_three_days_either_side():
    for gap, expected in [(0, True), (3, True), (4, False)]:
        for sign in (1, -1):
            candidate = tx("-5.00", 10 + sign * gap)
            found = reconcile_candidate(row("-5.00", 10), [candidate], set())
            assert (found is candidate) is expected


def test_a_candidate_already_conciliated_or_from_the_bank_is_skipped():
    assert reconcile_candidate(row("-5.00", 1), [tx("-5.00", 1, bank_ref="abc")], set()) is None
    assert reconcile_candidate(row("-5.00", 1), [tx("-5.00", 1, source="banco:X")], set()) is None
    used = tx("-5.00", 1)
    assert reconcile_candidate(row("-5.00", 1), [used], {used.id}) is None
