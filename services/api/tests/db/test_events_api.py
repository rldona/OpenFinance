"""OF-1603: eventos y viajes que agrupan gastos compartidos."""

from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.db.conftest import CSRF
from tests.db.test_members_api import accept, invite
from tests.db.test_sharing_api import DAY, expense, guest, me, money


def make_event(client, name="Roma", **extra):
    r = client.post("/api/v1/sharing/events", json={"name": name, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def in_event(client, event, amount, payers, shares, **extra):
    return expense(client, amount, payers, shares=shares, event_id=event["id"], **extra)


def cat(client, slug="super") -> str:
    return next(c["id"] for c in client.get("/api/v1/categories").json() if c["slug"] == slug)


def test_create_list_update_and_the_defaults(as_raul, as_elena, seed):
    trip = make_event(as_raul, starts_on="2026-12-01", ends_on="2026-12-07")
    assert trip["icon"] == "🧳" and trip["closed"] is False
    assert [e["name"] for e in as_elena.get("/api/v1/sharing/events").json()] == [
        "Roma"
    ]  # del hogar
    updated = as_raul.put(
        f"/api/v1/sharing/events/{trip['id']}", json={"name": "Roma y Florencia", "icon": "🇮🇹"}
    )
    assert updated.status_code == 200 and updated.json()["name"] == "Roma y Florencia"
    assert updated.json()["starts_on"] is None


def test_invalid_events_are_rejected(as_raul, seed):
    bad = [
        {"name": "   "},
        {"name": "x" * 81},
        {"name": "Roma", "starts_on": "2026-12-07", "ends_on": "2026-12-01"},
        {"name": "Roma", "icon": ""},
    ]
    for body in bad:
        assert as_raul.post("/api/v1/sharing/events", json=body).status_code == 422, body


def test_the_summary_has_total_who_paid_balances_and_categories(as_raul, as_elena, seed):
    raul, elena, marta = me(as_raul), me(as_elena), guest(as_raul)
    trip = make_event(as_raul)
    everyone = [(raul, None), (elena, None), (marta, None)]
    food, fun = cat(as_raul), cat(as_raul, "restaurantes")
    in_event(as_raul, trip, "90.00", [(raul, "90.00")], everyone, category_id=food)
    in_event(as_elena, trip, "30.00", [(elena, "30.00")], everyone, category_id=fun)
    expense(as_raul, "999.00", [(raul, "999.00")], shares=[(raul, None)])  # otro gasto, sin evento
    body = as_raul.get(f"/api/v1/sharing/events/{trip['id']}").json()
    assert money(body["total"]) == Decimal("120.00") and body["count"] == 2
    by_name = {b["participant"]["name"]: b for b in body["balances"]}
    assert money(by_name["Raúl"]["paid"]) == Decimal("90.00")
    assert money(by_name["Raúl"]["share"]) == Decimal("40.00")
    assert money(by_name["Raúl"]["net"]) == Decimal("50.00")
    assert money(by_name["Elena"]["net"]) == Decimal("-10.00")
    assert money(by_name["Marta"]["net"]) == Decimal("-40.00")
    assert sum(money(b["net"]) for b in body["balances"]) == 0
    assert {c["name"]: money(c["amount"]) for c in body["by_category"]} == {
        "Supermercado": Decimal("90.00"),
        "Restaurantes": Decimal("30.00"),
    }
    assert [e["description"] for e in body["expenses"]] == ["Luz", "Luz"]
    left = {b["participant"]["id"]: money(b["net"]) for b in body["balances"]}
    for t in body["suggestions"]:
        left[t["from_id"]] += money(t["amount"])
        left[t["to_id"]] -= money(t["amount"])
    assert all(v == 0 for v in left.values())


def test_event_balances_use_only_its_own_expenses_not_settlements(as_raul, as_elena, seed):
    raul, elena = me(as_raul), me(as_elena)
    trip = make_event(as_raul)
    in_event(as_raul, trip, "60.00", [(raul, "60.00")], [(raul, None), (elena, None)])
    paid = as_elena.post(
        "/api/v1/sharing/settlements",
        json={"from_id": elena, "to_id": raul, "amount": "30.00", "on": DAY},
    ).json()
    as_raul.post(f"/api/v1/sharing/settlements/{paid['id']}/confirm")
    body = as_raul.get(f"/api/v1/sharing/events/{trip['id']}").json()
    assert {b["participant"]["name"]: money(b["net"]) for b in body["balances"]}[
        "Elena"
    ] == Decimal("-30.00")
    # pero el saldo del grupo sí recoge el pago
    nets = {
        b["participant"]["name"]: money(b["net"])
        for b in as_raul.get("/api/v1/sharing/balances").json()["balances"]
    }
    assert nets["Elena"] == 0


def test_voided_expenses_leave_the_summary(as_raul, seed):
    raul = me(as_raul)
    trip = make_event(as_raul)
    created = in_event(as_raul, trip, "50.00", [(raul, "50.00")], [(raul, None)]).json()
    as_raul.delete(f"/api/v1/sharing/expenses/{created['id']}")
    body = as_raul.get(f"/api/v1/sharing/events/{trip['id']}").json()
    assert money(body["total"]) == 0 and body["count"] == 0 and body["expenses"] == []


def test_a_closed_event_takes_no_new_expenses_and_can_reopen(as_raul, seed):
    raul = me(as_raul)
    trip = make_event(as_raul)
    first = in_event(as_raul, trip, "50.00", [(raul, "50.00")], [(raul, None)]).json()
    assert as_raul.post(f"/api/v1/sharing/events/{trip['id']}/close").json()["closed"] is True
    assert in_event(as_raul, trip, "10.00", [(raul, "10.00")], [(raul, None)]).status_code == 409
    assert as_raul.delete(f"/api/v1/sharing/expenses/{first['id']}").status_code == 409
    body = {
        "on": DAY, "description": "Cambio", "amount": "50.00", "method": "equal",
        "event_id": trip["id"],
        "payers": [{"participant_id": raul, "amount": "50.00"}],
        "shares": [{"participant_id": raul}],
    }  # fmt: skip
    assert as_raul.put(f"/api/v1/sharing/expenses/{first['id']}", json=body).status_code == 409
    assert as_raul.get(f"/api/v1/sharing/events/{trip['id']}").status_code == 200  # leer sí
    as_raul.post(f"/api/v1/sharing/events/{trip['id']}/reopen")
    assert in_event(as_raul, trip, "10.00", [(raul, "10.00")], [(raul, None)]).status_code == 201


def test_an_expense_can_move_between_events_but_not_into_a_closed_one(as_raul, seed):
    raul = me(as_raul)
    a, b = make_event(as_raul, "A"), make_event(as_raul, "B")
    created = in_event(as_raul, a, "20.00", [(raul, "20.00")], [(raul, None)]).json()
    body = {
        "on": DAY, "description": "Luz", "amount": "20.00", "method": "equal",
        "event_id": b["id"],
        "payers": [{"participant_id": raul, "amount": "20.00"}],
        "shares": [{"participant_id": raul}],
    }  # fmt: skip
    assert (
        as_raul.put(f"/api/v1/sharing/expenses/{created['id']}", json=body).json()["event_id"]
        == b["id"]
    )
    assert as_raul.get(f"/api/v1/sharing/events/{a['id']}").json()["count"] == 0
    as_raul.post(f"/api/v1/sharing/events/{a['id']}/close")
    body["event_id"] = a["id"]
    assert as_raul.put(f"/api/v1/sharing/expenses/{created['id']}", json=body).status_code == 409


def test_an_event_with_expenses_is_closed_not_deleted(as_raul, seed):
    raul = me(as_raul)
    empty, used = make_event(as_raul, "Vacío"), make_event(as_raul, "Con gastos")
    assert as_raul.delete(f"/api/v1/sharing/events/{empty['id']}").status_code == 204
    created = in_event(as_raul, used, "5.00", [(raul, "5.00")], [(raul, None)]).json()
    assert as_raul.delete(f"/api/v1/sharing/events/{used['id']}").status_code == 409
    as_raul.delete(f"/api/v1/sharing/expenses/{created['id']}")  # anulado sigue contando
    assert as_raul.delete(f"/api/v1/sharing/events/{used['id']}").status_code == 409
    assert [e["name"] for e in as_raul.get("/api/v1/sharing/events").json()] == ["Con gastos"]


def test_an_unknown_event_is_404(as_raul, seed):
    raul = me(as_raul)
    r = expense(as_raul, "5.00", [(raul, "5.00")], shares=[(raul, None)], event_id=str(uuid4()))
    assert r.status_code == 404
    assert as_raul.get(f"/api/v1/sharing/events/{uuid4()}").status_code == 404


def test_another_household_sees_and_touches_nothing(as_raul, as_ana, seed):
    raul = me(as_raul)
    trip = make_event(as_raul)
    in_event(as_raul, trip, "5.00", [(raul, "5.00")], [(raul, None)])
    assert as_ana.get("/api/v1/sharing/events").json() == []
    assert as_ana.get(f"/api/v1/sharing/events/{trip['id']}").status_code == 404
    for call in (
        lambda: as_ana.put(f"/api/v1/sharing/events/{trip['id']}", json={"name": "Mío"}),
        lambda: as_ana.post(f"/api/v1/sharing/events/{trip['id']}/close"),
        lambda: as_ana.post(f"/api/v1/sharing/events/{trip['id']}/reopen"),
        lambda: as_ana.delete(f"/api/v1/sharing/events/{trip['id']}"),
    ):
        assert call().status_code == 404
    ana = me(as_ana)
    r = expense(as_ana, "5.00", [(ana, "5.00")], shares=[(ana, None)], event_id=trip["id"])
    assert r.status_code == 404  # ni se puede colgar un gasto de un evento ajeno


def test_a_viewer_reads_events_but_cannot_change_them(app, as_raul, seed):
    trip = make_event(as_raul)
    viewer, _ = accept(app, invite(as_raul, "viewer")["token"], email="mira@example.org")
    assert viewer.get(f"/api/v1/sharing/events/{trip['id']}").status_code == 200
    assert viewer.post("/api/v1/sharing/events", json={"name": "X"}).status_code == 403
    assert viewer.post(f"/api/v1/sharing/events/{trip['id']}/close").status_code == 403
    assert viewer.delete(f"/api/v1/sharing/events/{trip['id']}").status_code == 403


def test_requires_a_session(app, seed):
    anonymous = TestClient(app, headers=CSRF)
    assert anonymous.get("/api/v1/sharing/events").status_code == 401
