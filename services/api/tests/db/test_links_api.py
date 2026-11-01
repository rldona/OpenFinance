"""OF-1004: traspasos enlazados entre cuentas propias."""

# ruff: noqa: DTZ001  (la hora local del banco no lleva zona)
from datetime import datetime
from uuid import uuid4

import pytest

from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork


def add(session_factory, account, description, amount, when, kind=TransactionKind.EXPENSE) -> str:
    tid = TransactionId(uuid4())
    with session_factory() as s:
        SqlUnitOfWork(s).transactions.add(
            Transaction(
                id=tid,
                household_id=account.household_id,
                account_id=account.id,
                booked_at=when,
                value_date=when.date(),
                description=description,
                amount=Money.of(amount, "EUR"),
                kind=kind,
            )
        )
        s.commit()
    return str(tid)


def get(client, tid: str) -> dict:
    rows = client.get("/api/v1/transactions").json()
    return next(t for t in rows if t["id"] == tid)


def link(client, tid: str, peer: str):
    return client.put(f"/api/v1/transactions/{tid}/link", json={"peer_id": peer})


@pytest.fixture
def pair(session_factory, seed):
    out = add(
        session_factory,
        seed.raul_personal,
        "Traspaso a la conjunta",
        "-50.00",
        datetime(2026, 10, 10, 9),
    )
    inn = add(
        session_factory,
        seed.joint,
        "Traspaso de Raul",
        "50.00",
        datetime(2026, 10, 11, 9),
        TransactionKind.INCOME,
    )
    return out, inn


class TestLink:
    def test_links_both_sides_and_stops_counting_them(self, as_raul, seed, pair) -> None:
        out, inn = pair
        before = as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        r = link(as_raul, out, inn)
        assert r.status_code == 200
        body = r.json()
        assert body["transaction"]["transfer_peer_id"] == inn
        assert body["peer"]["transfer_peer_id"] == out
        assert {body["transaction"]["kind"], body["peer"]["kind"]} == {"internal_transfer"}
        assert get(as_raul, inn)["transfer_peer_id"] == out
        # El ingreso de 50 € ya no es ingreso del hogar.
        after = as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert float(after["income"]["amount"]) == float(before["income"]["amount"]) - 50

    def test_keeps_kinds_that_already_mean_something(self, as_raul, seed) -> None:
        rows = as_raul.get("/api/v1/transactions", params={"month": "2026-10"}).json()
        payment = next(t for t in rows if t["description"] == "Payment from Raul")
        aport = next(t for t in rows if t["description"] == "Aportación casa")
        r = link(as_raul, aport["id"], payment["id"])
        assert r.status_code == 200
        assert r.json()["transaction"]["kind"] == "contribution"
        assert r.json()["peer"]["kind"] == "contribution"

    def test_undo_and_redo_restore_kinds_and_link(self, as_raul, seed, pair) -> None:
        out, inn = pair
        op = link(as_raul, out, inn).json()["operation_id"]
        assert as_raul.post(f"/api/v1/changes/{op}/undo").json()["kept"] == 0
        assert get(as_raul, out)["transfer_peer_id"] is None
        assert (get(as_raul, out)["kind"], get(as_raul, inn)["kind"]) == ("expense", "income")
        assert as_raul.post(f"/api/v1/changes/{op}/redo").status_code == 200
        assert get(as_raul, out)["transfer_peer_id"] == inn
        assert get(as_raul, inn)["kind"] == "internal_transfer"

    def test_unlink_and_its_undo(self, as_raul, seed, pair) -> None:
        out, inn = pair
        link(as_raul, out, inn)
        r = as_raul.delete(f"/api/v1/transactions/{inn}/link")
        assert r.status_code == 200
        assert get(as_raul, out)["transfer_peer_id"] is None
        assert get(as_raul, inn)["transfer_peer_id"] is None
        assert as_raul.post(f"/api/v1/changes/{r.json()['operation_id']}/undo").status_code == 200
        assert get(as_raul, out)["transfer_peer_id"] == inn
        assert (
            as_raul.delete(f"/api/v1/transactions/{get(as_raul, out)['id']}/link").status_code
            == 200
        )
        assert as_raul.delete(f"/api/v1/transactions/{out}/link").status_code == 422

    def test_candidates(self, as_raul, seed, pair, session_factory) -> None:
        out, inn = pair
        add(
            session_factory,
            seed.joint,
            "Lejos",
            "50.00",
            datetime(2026, 10, 25, 9),
            TransactionKind.INCOME,
        )
        add(
            session_factory,
            seed.joint,
            "Otro importe",
            "51.00",
            datetime(2026, 10, 11, 9),
            TransactionKind.INCOME,
        )
        found = as_raul.get(f"/api/v1/transactions/{out}/transfer-candidates").json()
        assert [t["id"] for t in found] == [inn]
        link(as_raul, out, inn)
        assert as_raul.get(f"/api/v1/transactions/{out}/transfer-candidates").json() == []

    @pytest.mark.parametrize(
        "case",
        ["same_account", "different_amount", "same_sign", "self"],
    )
    def test_invalid_pairs_are_422(self, as_raul, seed, session_factory, pair, case) -> None:
        out, _ = pair
        if case == "same_account":
            peer = add(
                session_factory,
                seed.raul_personal,
                "Otro",
                "50.00",
                datetime(2026, 10, 10, 9),
                TransactionKind.INCOME,
            )
        elif case == "different_amount":
            peer = add(
                session_factory,
                seed.joint,
                "Otro",
                "49.00",
                datetime(2026, 10, 10, 9),
                TransactionKind.INCOME,
            )
        elif case == "same_sign":
            peer = add(session_factory, seed.joint, "Otro", "-50.00", datetime(2026, 10, 10, 9))
        else:
            peer = out
        assert link(as_raul, out, peer).status_code == 422
        assert get(as_raul, out)["kind"] == "expense"

    def test_a_movement_cannot_be_in_two_transfers(
        self, as_raul, seed, pair, session_factory
    ) -> None:
        out, inn = pair
        link(as_raul, out, inn)
        other = add(
            session_factory,
            seed.joint,
            "Otro",
            "50.00",
            datetime(2026, 10, 10, 9),
            TransactionKind.INCOME,
        )
        assert link(as_raul, out, other).status_code == 409


class TestPrivacy:
    def test_cannot_link_to_a_movement_you_cannot_see(
        self, as_raul, as_elena, seed, session_factory
    ) -> None:
        hers = add(
            session_factory,
            seed.elena_personal,
            "Traspaso de Elena",
            "-80.00",
            datetime(2026, 10, 10, 9),
        )
        mine = add(
            session_factory,
            seed.joint,
            "Entrada",
            "80.00",
            datetime(2026, 10, 10, 9),
            TransactionKind.INCOME,
        )
        assert link(as_raul, mine, hers).status_code == 404
        assert link(as_raul, hers, mine).status_code == 404
        assert as_raul.get(f"/api/v1/transactions/{mine}/transfer-candidates").json() == []

    def test_the_partner_sees_no_trace_of_a_link_to_a_personal_account(
        self, as_raul, as_elena, seed, session_factory
    ) -> None:
        hers = add(
            session_factory,
            seed.elena_personal,
            "Traspaso de Elena",
            "-80.00",
            datetime(2026, 10, 10, 9),
        )
        shared = add(
            session_factory,
            seed.joint,
            "Entrada",
            "80.00",
            datetime(2026, 10, 10, 9),
            TransactionKind.INCOME,
        )
        r = link(as_elena, hers, shared)
        assert r.status_code == 200 and r.json()["transaction"]["transfer_peer_id"] == shared
        # Raúl ve la entrada en la conjunta, pero no sabe de qué cuenta personal viene.
        assert get(as_raul, shared)["transfer_peer_id"] is None
        assert get(as_raul, shared)["kind"] == "internal_transfer"
        assert as_raul.delete(f"/api/v1/transactions/{shared}/link").status_code == 422
        assert hers not in str(as_raul.get("/api/v1/export", params={"format": "json"}).json())

    def test_other_households_get_404(self, as_ana, seed, pair) -> None:
        out, inn = pair
        assert link(as_ana, out, inn).status_code == 404

    def test_partners_undo_is_404(self, as_raul, as_elena, seed, pair) -> None:
        out, inn = pair
        op = link(as_raul, out, inn).json()["operation_id"]
        assert as_elena.post(f"/api/v1/changes/{op}/undo").status_code == 404


def test_the_export_carries_visible_links_only(as_raul, as_elena, seed, session_factory) -> None:
    out = add(session_factory, seed.raul_personal, "A", "-30.00", datetime(2026, 10, 10, 9))
    inn = add(
        session_factory, seed.joint, "B", "30.00", datetime(2026, 10, 10, 9), TransactionKind.INCOME
    )
    link(as_raul, out, inn)
    data = as_raul.get("/api/v1/export", params={"format": "json"}).json()
    peers = {t["id"]: t["transfer_peer_id"] for t in data["transactions"]}
    assert peers[out] == inn and peers[inn] == out
    theirs = {
        t["id"]: t["transfer_peer_id"]
        for t in as_elena.get("/api/v1/export", params={"format": "json"}).json()["transactions"]
    }
    assert theirs[inn] is None and out not in theirs
