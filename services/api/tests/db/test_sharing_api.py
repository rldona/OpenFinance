"""OF-1602: reparto de gastos, saldos y liquidaciones."""

from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.db.conftest import CSRF
from tests.db.test_members_api import accept, invite

DAY = "2026-11-01"


def me(client) -> str:
    return client.get("/api/v1/me").json()["user"]["id"]


def guest(client, name="Marta"):
    r = client.post("/api/v1/sharing/guests", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def money(m) -> Decimal:
    return Decimal(m["amount"])


def expense(client, amount, payers, method="equal", shares=None, **extra):
    body = {
        "on": DAY,
        "description": "Luz",
        "amount": amount,
        "payers": [{"participant_id": p, "amount": a} for p, a in payers],
        "method": method,
        "shares": [{"participant_id": p, "value": v} for p, v in (shares or [])],
        **extra,
    }
    return client.post("/api/v1/sharing/expenses", json=body)


def nets(client) -> dict[str, Decimal]:
    body = client.get("/api/v1/sharing/balances").json()
    return {b["participant"]["id"]: money(b["net"]) for b in body["balances"]}


# --- participantes ---------------------------------------------------------------------------


def test_participants_are_the_household_and_its_guests(as_raul, as_elena, seed):
    marta = guest(as_raul)
    listed = as_raul.get("/api/v1/sharing/participants").json()
    assert {(p["name"], p["is_guest"]) for p in listed} == {
        ("Raúl", False),
        ("Elena", False),
        ("Marta", True),
    }
    assert marta in {p["id"] for p in listed}
    # Elena, del mismo hogar, ve lo mismo
    assert {p["name"] for p in as_elena.get("/api/v1/sharing/participants").json()} == {
        "Raúl",
        "Elena",
        "Marta",
    }


# --- gastos ----------------------------------------------------------------------------------


def test_an_equal_split_sums_exactly_and_balances_sum_to_zero(as_raul, as_elena, seed):
    raul, elena, marta = me(as_raul), me(as_elena), guest(as_raul)
    r = expense(
        as_raul, "100.00", [(raul, "100.00")], shares=[(raul, None), (elena, None), (marta, None)]
    )
    assert r.status_code == 201, r.text
    parts = [money(p["amount"]) for p in r.json()["parts"]]
    assert sorted(parts) == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert sum(parts) == Decimal("100.00")
    result = nets(as_raul)
    assert result[raul] == Decimal("66.66")
    assert result[elena] == result[marta] == Decimal("-33.33")
    assert sum(result.values()) == 0


def test_the_other_methods_through_the_api(as_raul, as_elena, seed):
    raul, elena = me(as_raul), me(as_elena)
    shared = [(raul, "60"), (elena, "40")]
    pct = expense(as_raul, "50.00", [(raul, "50.00")], "percentage", shares=shared)
    assert [money(p["amount"]) for p in pct.json()["parts"]] == [Decimal("30.00"), Decimal("20.00")]
    exact = expense(
        as_raul, "50.00", [(raul, "50.00")], "exact", shares=[(raul, "12.50"), (elena, "37.50")]
    )
    assert [money(p["amount"]) for p in exact.json()["parts"]] == [
        Decimal("12.50"),
        Decimal("37.50"),
    ]
    weights = expense(
        as_raul, "90.00", [(raul, "90.00")], "shares", shares=[(raul, "2"), (elena, "1")]
    )
    assert [money(p["amount"]) for p in weights.json()["parts"]] == [
        Decimal("60.00"),
        Decimal("30.00"),
    ]


def test_a_subset_of_the_group_can_share(as_raul, as_elena, seed):
    raul, elena, marta = me(as_raul), me(as_elena), guest(as_raul)
    expense(as_raul, "20.00", [(raul, "20.00")], shares=[(raul, None), (marta, None)])
    result = nets(as_raul)
    assert (
        result[elena] == 0
        and result[raul] == Decimal("10.00")
        and result[marta] == Decimal("-10.00")
    )


def test_several_people_can_pay(as_raul, as_elena, seed):
    raul, elena = me(as_raul), me(as_elena)
    expense(
        as_raul, "100.00", [(raul, "70.00"), (elena, "30.00")], shares=[(raul, None), (elena, None)]
    )
    result = nets(as_raul)
    assert result[raul] == Decimal("20.00") and result[elena] == Decimal("-20.00")


def test_what_does_not_add_up_is_rejected(as_raul, as_elena, seed):
    raul, elena = me(as_raul), me(as_elena)
    both = [(raul, None), (elena, None)]
    assert expense(as_raul, "100.00", [(raul, "99.99")], shares=both).status_code == 422
    assert (
        expense(
            as_raul, "100.00", [(raul, "100.00")], "percentage", [(raul, "50"), (elena, "49")]
        ).status_code
        == 422
    )
    assert (
        expense(
            as_raul, "100.00", [(raul, "100.00")], "exact", [(raul, "50"), (elena, "49.99")]
        ).status_code
        == 422
    )
    assert (
        expense(
            as_raul, "100.00", [(raul, "100.00")], "shares", [(raul, "1"), (elena, "0")]
        ).status_code
        == 422
    )
    assert expense(as_raul, "0", [(raul, "0")], shares=both).status_code == 422
    assert expense(as_raul, "-5", [(raul, "-5")], shares=both).status_code == 422
    assert expense(as_raul, "abc", [(raul, "100")], shares=both).status_code == 422
    assert (
        expense(as_raul, "100", [(raul, "100")], shares=[(raul, None), (raul, None)]).status_code
        == 422
    )
    assert expense(as_raul, "100", [(raul, "50"), (raul, "50")], shares=both).status_code == 422
    assert as_raul.get("/api/v1/sharing/expenses").json() == []  # nada a medias


def test_people_outside_the_household_cannot_take_part(as_raul, as_ana, seed):
    raul, ana = me(as_raul), me(as_ana)
    r = expense(as_raul, "10.00", [(raul, "10.00")], shares=[(raul, None), (ana, None)])
    assert r.status_code == 422
    other_guest = guest(as_ana, "Del vecino")
    assert (
        expense(
            as_raul, "10.00", [(raul, "10.00")], shares=[(raul, None), (other_guest, None)]
        ).status_code
        == 422
    )


def test_unknown_category_is_404(as_raul, seed):
    raul = me(as_raul)
    r = expense(
        as_raul, "10.00", [(raul, "10.00")], shares=[(raul, None)], category_id=str(uuid4())
    )
    assert r.status_code == 404


def test_preview_matches_what_is_stored(as_raul, as_elena, seed):
    raul, elena = me(as_raul), me(as_elena)
    body = {
        "amount": "10.01",
        "method": "equal",
        "shares": [{"participant_id": raul}, {"participant_id": elena}],
    }
    preview = as_raul.post("/api/v1/sharing/split-preview", json=body).json()
    stored = expense(
        as_raul, "10.01", [(raul, "10.01")], shares=[(raul, None), (elena, None)]
    ).json()["parts"]
    assert preview == stored
    assert (
        as_raul.post("/api/v1/sharing/split-preview", json={**body, "amount": "0"}).status_code
        == 422
    )


def test_correcting_recomputes_and_voiding_removes_it_from_the_balances(as_raul, as_elena, seed):
    raul, elena = me(as_raul), me(as_elena)
    created = expense(
        as_raul, "100.00", [(raul, "100.00")], shares=[(raul, None), (elena, None)]
    ).json()
    assert nets(as_raul)[elena] == Decimal("-50.00")
    body = {
        "on": DAY, "description": "Luz corregida", "amount": "60.00", "method": "equal",
        "payers": [{"participant_id": raul, "amount": "60.00"}],
        "shares": [{"participant_id": raul}, {"participant_id": elena}],
    }  # fmt: skip
    updated = as_raul.put(f"/api/v1/sharing/expenses/{created['id']}", json=body)
    assert updated.status_code == 200 and updated.json()["description"] == "Luz corregida"
    assert nets(as_raul)[elena] == Decimal("-30.00")
    assert as_raul.delete(f"/api/v1/sharing/expenses/{created['id']}").status_code == 204
    assert all(v == 0 for v in nets(as_raul).values())
    assert as_raul.get("/api/v1/sharing/expenses").json() == []
    assert as_raul.put(f"/api/v1/sharing/expenses/{created['id']}", json=body).status_code == 409


def test_balances_follow_the_adr_example_and_suggest_who_pays_whom(as_raul, as_elena, seed):
    ana, elena, marta = me(as_raul), me(as_elena), guest(as_raul)  # «Ana» = quien paga
    expense(as_raul, "90.00", [(ana, "90.00")], shares=[(ana, None), (elena, None), (marta, None)])
    body = as_raul.get("/api/v1/sharing/balances").json()
    assert {t["from_id"] for t in body["suggestions"]} == {elena, marta}
    assert all(
        t["to_id"] == ana and money(t["amount"]) == Decimal("30.00") for t in body["suggestions"]
    )
    by_name = {b["participant"]["name"]: b for b in body["balances"]}
    assert money(by_name["Raúl"]["paid"]) == Decimal("90.00") and money(
        by_name["Raúl"]["share"]
    ) == Decimal("30.00")


# --- liquidaciones ---------------------------------------------------------------------------


def settle(client, frm, to, amount="30.00", reference=None):
    return client.post(
        "/api/v1/sharing/settlements",
        json={"from_id": frm, "to_id": to, "amount": amount, "on": DAY, "reference": reference},
    )


def seeded_debt(as_raul, as_elena):
    raul, elena = me(as_raul), me(as_elena)
    expense(as_raul, "60.00", [(raul, "60.00")], shares=[(raul, None), (elena, None)])
    return raul, elena


def test_a_settlement_needs_confirmation_by_the_receiver(as_raul, as_elena, seed):
    raul, elena = seeded_debt(as_raul, as_elena)
    created = settle(as_elena, elena, raul)
    assert created.status_code == 201 and created.json()["status"] == "pending"
    assert nets(as_raul)[elena] == Decimal("-30.00")  # pendiente: no cambia nada
    sid = created.json()["id"]
    assert (
        as_elena.post(f"/api/v1/sharing/settlements/{sid}/confirm").status_code == 403
    )  # no es quien recibe
    assert (
        as_raul.post(f"/api/v1/sharing/settlements/{sid}/confirm").json()["status"] == "confirmed"
    )
    assert nets(as_raul)[elena] == 0 and nets(as_raul)[raul] == 0
    assert as_raul.post(f"/api/v1/sharing/settlements/{sid}/confirm").status_code == 409


def test_registering_the_same_reference_does_not_duplicate(as_raul, as_elena, seed):
    raul, elena = seeded_debt(as_raul, as_elena)
    first = settle(as_elena, elena, raul, reference="bizum-1234")
    again = settle(as_elena, elena, raul, reference="bizum-1234")
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert len(as_raul.get("/api/v1/sharing/settlements").json()) == 1
    other = settle(as_elena, elena, raul, amount="12.00", reference="bizum-1234")
    assert other.status_code == 409


def test_you_register_what_you_pay_not_what_others_pay(as_raul, as_elena, seed):
    raul, elena = seeded_debt(as_raul, as_elena)
    assert settle(as_raul, elena, raul).status_code == 403  # Raúl no registra lo que paga Elena
    assert settle(as_elena, elena, elena).status_code == 422
    assert settle(as_elena, elena, raul, amount="0").status_code == 422
    assert settle(as_elena, elena, str(uuid4())).status_code == 422


def test_a_guest_settles_through_whoever_edits(as_raul, as_elena, seed):
    raul, marta = me(as_raul), guest(as_raul)
    expense(as_raul, "40.00", [(raul, "40.00")], shares=[(raul, None), (marta, None)])
    paid = settle(as_elena, marta, raul, amount="20.00")  # Elena anota por Marta, que paga a Raúl
    assert paid.status_code == 201
    assert (
        as_raul.post(f"/api/v1/sharing/settlements/{paid.json()['id']}/confirm").status_code == 200
    )
    assert nets(as_raul)[marta] == 0
    # al revés: si recibe un invitado, lo confirma cualquiera que edite
    expense(as_raul, "40.00", [(marta, "40.00")], shares=[(raul, None), (marta, None)])
    owed = settle(as_raul, raul, marta, amount="20.00")
    assert (
        as_elena.post(f"/api/v1/sharing/settlements/{owed.json()['id']}/confirm").status_code == 200
    )


def test_cancelling_a_pending_settlement(as_raul, as_elena, seed):
    raul, elena = seeded_debt(as_raul, as_elena)
    sid = settle(as_elena, elena, raul).json()["id"]
    assert as_raul.post(f"/api/v1/sharing/settlements/{sid}/cancel").status_code == 200  # owner
    assert as_elena.post(f"/api/v1/sharing/settlements/{sid}/confirm").status_code == 409
    sid2 = settle(as_elena, elena, raul).json()["id"]
    assert (
        as_elena.post(f"/api/v1/sharing/settlements/{sid2}/cancel").json()["status"] == "cancelled"
    )
    assert nets(as_raul)[elena] == Decimal("-30.00")


def test_balances_keep_summing_to_zero_with_everything_mixed(as_raul, as_elena, seed):
    raul, elena, marta = me(as_raul), me(as_elena), guest(as_raul)
    people = [(raul, None), (elena, None), (marta, None)]
    expense(as_raul, "100.01", [(raul, "100.01")], shares=people)
    expense(
        as_elena,
        "33.33",
        [(elena, "20.00"), (marta, "13.33")],
        "shares",
        [(raul, "2"), (elena, "1"), (marta, "1")],
    )
    expense(
        as_raul,
        "7.77",
        [(marta, "7.77")],
        "percentage",
        [(raul, "10.5"), (elena, "39.5"), (marta, "50")],
    )
    sid = settle(as_elena, elena, raul, amount="10.00").json()["id"]
    as_raul.post(f"/api/v1/sharing/settlements/{sid}/confirm")
    assert sum(nets(as_raul).values()) == 0
    body = as_raul.get("/api/v1/sharing/balances").json()
    left = dict(nets(as_raul))
    for t in body["suggestions"]:
        left[t["from_id"]] += money(t["amount"])
        left[t["to_id"]] -= money(t["amount"])
    assert all(v == 0 for v in left.values())


# --- invitados y personas que se van ---------------------------------------------------------


def test_a_guest_is_archived_only_with_a_zero_balance(as_raul, as_elena, seed):
    raul, marta = me(as_raul), guest(as_raul)
    created = expense(
        as_raul, "10.00", [(raul, "10.00")], shares=[(raul, None), (marta, None)]
    ).json()
    assert as_raul.post(f"/api/v1/sharing/guests/{marta}/archive").status_code == 422
    sid = settle(as_raul, marta, raul, amount="5.00").json()["id"]
    assert as_raul.post(f"/api/v1/sharing/guests/{marta}/archive").status_code == 422  # pendiente
    as_raul.post(f"/api/v1/sharing/settlements/{sid}/confirm")
    assert as_raul.post(f"/api/v1/sharing/guests/{marta}/archive").status_code == 204
    again = expense(as_raul, "10.00", [(raul, "10.00")], shares=[(raul, None), (marta, None)])
    assert again.status_code == 422  # un invitado archivado no se usa más
    assert created["id"]


def test_someone_who_leaves_stays_in_what_was_already_shared(app, as_raul, seed):
    joined, r = accept(app, invite(as_raul)["token"], email="se-va@example.org", name="Se Va")
    assert r.status_code == 201
    leaver, raul = me(joined), me(as_raul)
    expense(as_raul, "50.00", [(raul, "50.00")], shares=[(raul, None), (leaver, None)])
    assert as_raul.delete(f"/api/v1/household/members/{leaver}").status_code == 204
    rows = as_raul.get("/api/v1/sharing/balances").json()["balances"]
    gone = next(b for b in rows if b["participant"]["id"] == leaver)
    assert gone["participant"]["active"] is False and money(gone["net"]) == Decimal("-25.00")
    assert sum(money(b["net"]) for b in rows) == 0


# --- otros hogares y sesión ------------------------------------------------------------------


def test_another_household_sees_and_touches_nothing(as_raul, as_ana, seed):
    raul = me(as_raul)
    created = expense(as_raul, "10.00", [(raul, "10.00")], shares=[(raul, None)]).json()
    marta = guest(as_raul)
    sid = settle(as_raul, raul, marta).json()["id"]
    assert as_ana.get("/api/v1/sharing/expenses").json() == []
    assert as_ana.get("/api/v1/sharing/settlements").json() == []
    assert {p["name"] for p in as_ana.get("/api/v1/sharing/participants").json()} == {"Ana"}
    assert as_ana.delete(f"/api/v1/sharing/expenses/{created['id']}").status_code == 404
    assert as_ana.post(f"/api/v1/sharing/settlements/{sid}/confirm").status_code == 404
    assert as_ana.post(f"/api/v1/sharing/settlements/{sid}/cancel").status_code == 404
    assert as_ana.post(f"/api/v1/sharing/guests/{marta}/archive").status_code == 404
    assert len(as_raul.get("/api/v1/sharing/expenses").json()) == 1


def test_a_viewer_reads_the_group_but_cannot_change_it(app, as_raul, seed):
    raul = me(as_raul)
    expense(as_raul, "10.00", [(raul, "10.00")], shares=[(raul, None)])
    viewer, _ = accept(app, invite(as_raul, "viewer")["token"], email="mira@example.org")
    assert len(viewer.get("/api/v1/sharing/expenses").json()) == 1
    assert viewer.get("/api/v1/sharing/balances").status_code == 200
    assert viewer.post("/api/v1/sharing/guests", json={"name": "X"}).status_code == 403
    assert (
        expense(viewer, "10.00", [(me(viewer), "10.00")], shares=[(me(viewer), None)]).status_code
        == 403
    )


def test_requires_a_session(app, seed):
    anonymous = TestClient(app, headers=CSRF)
    assert anonymous.get("/api/v1/sharing/expenses").status_code == 401
    assert anonymous.get("/api/v1/sharing/balances").status_code == 401
