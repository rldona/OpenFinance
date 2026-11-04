"""OF-1201: pagos programados, ocurrencias y privacidad."""

from datetime import timedelta

from openfinance.infrastructure.time import local_today

TODAY = local_today()


def body(seed, **kw):
    return {
        "name": "Alquiler",
        "amount": "-900.00",
        "account_id": str(seed.joint.id),
        "frequency": "monthly",
        "first_due": (TODAY + timedelta(days=5)).isoformat(),
        **kw,
    }


def create(client, seed, **kw):
    return client.post("/api/v1/schedule", json=body(seed, **kw))


def pay(client, seed, amount, days_ago):
    r = client.post(
        "/api/v1/transactions",
        json={
            "booked_on": (TODAY - timedelta(days=days_ago)).isoformat(),
            "description": "Pago",
            "amount": amount,
            "kind": "expense",
            "account_id": str(seed.joint.id),
        },
    )
    assert r.status_code == 201, r.text


class TestCrud:
    def test_create_list_update_delete_with_undo_and_redo(self, as_raul, seed) -> None:
        r = create(as_raul, seed)
        assert r.status_code == 201, r.text
        payment = r.json()["payment"]
        assert payment["amount"] == {"amount": "-900.00", "currency": "EUR"}
        listed = as_raul.get("/api/v1/schedule").json()
        assert [i["payment"]["name"] for i in listed] == ["Alquiler"]
        assert listed[0]["occurrences"][0]["status"] == "pending"

        up = as_raul.put(
            f"/api/v1/schedule/{payment['id']}",
            json=body(seed, name="Alquiler piso", amount="-950"),
        )
        assert up.json()["payment"]["name"] == "Alquiler piso"
        assert (
            as_raul.post(f"/api/v1/changes/{up.json()['operation_id']}/undo").json()["applied"] == 1
        )
        assert as_raul.get("/api/v1/schedule").json()[0]["payment"]["name"] == "Alquiler"

        gone = as_raul.delete(f"/api/v1/schedule/{payment['id']}").json()["operation_id"]
        assert as_raul.get("/api/v1/schedule").json() == []
        assert as_raul.post(f"/api/v1/changes/{gone}/undo").status_code == 200
        assert len(as_raul.get("/api/v1/schedule").json()) == 1
        assert (
            as_raul.post(f"/api/v1/changes/{r.json()['operation_id']}/undo").json()["applied"] == 1
        )
        assert as_raul.get("/api/v1/schedule").json() == []

    def test_an_unchanged_update_leaves_no_trace(self, as_raul, seed) -> None:
        payment = create(as_raul, seed).json()["payment"]
        r = as_raul.put(f"/api/v1/schedule/{payment['id']}", json=body(seed))
        assert r.status_code == 200 and r.json()["operation_id"] is None

    def test_rejects_what_makes_no_sense(self, as_raul, seed) -> None:
        assert create(as_raul, seed, amount="0").status_code == 422
        assert create(as_raul, seed, amount="mucho").status_code == 422
        assert create(as_raul, seed, frequency="once", interval=2).status_code == 422
        past = (TODAY - timedelta(days=30)).isoformat()
        assert create(as_raul, seed, ends_on=past).status_code == 422
        assert (
            create(as_raul, seed, category_id="00000000-0000-0000-0000-000000000000").status_code
            == 404
        )

    def test_a_name_is_not_repeated(self, as_raul, seed) -> None:
        assert create(as_raul, seed).status_code == 201
        assert create(as_raul, seed, name="alquiler").status_code == 409

    def test_the_horizon_is_bounded(self, as_raul) -> None:
        assert as_raul.get("/api/v1/schedule", params={"days": 0}).status_code == 422
        assert as_raul.get("/api/v1/schedule", params={"days": 401}).status_code == 422


class TestOccurrences:
    def test_unpaid_past_date_is_late_and_a_matching_charge_pays_it(self, as_raul, seed) -> None:
        create(as_raul, seed, first_due=(TODAY - timedelta(days=3)).isoformat())
        first = as_raul.get("/api/v1/schedule").json()[0]["occurrences"][0]
        assert first["status"] == "late"
        pay(as_raul, seed, "900.00", 3)
        first = as_raul.get("/api/v1/schedule").json()[0]["occurrences"][0]
        assert first["status"] == "paid" and first["transaction_id"]

    def test_a_charge_in_another_amount_does_not_pay_it(self, as_raul, seed) -> None:
        create(as_raul, seed, first_due=(TODAY - timedelta(days=3)).isoformat())
        pay(as_raul, seed, "400.00", 3)
        assert as_raul.get("/api/v1/schedule").json()[0]["occurrences"][0]["status"] == "late"

    def test_listing_never_writes_a_movement(self, as_raul, seed) -> None:
        create(as_raul, seed, first_due=(TODAY - timedelta(days=3)).isoformat())
        before = as_raul.get("/api/v1/transactions", params={"limit": 1000}).json()
        as_raul.get("/api/v1/schedule")
        assert as_raul.get("/api/v1/transactions", params={"limit": 1000}).json() == before

    def test_an_inactive_payment_has_no_occurrences(self, as_raul, seed) -> None:
        create(as_raul, seed, active=False)
        assert as_raul.get("/api/v1/schedule").json()[0]["occurrences"] == []


class TestPrivacy:
    def test_the_partner_personal_account_never_gets_a_payment_from_me(self, as_raul, seed) -> None:
        r = create(as_raul, seed, account_id=str(seed.elena_personal.id))
        assert r.status_code == 404

    def test_a_personal_payment_is_invisible_unchangeable_and_not_undoable_for_the_partner(
        self, as_raul, as_elena, seed
    ) -> None:
        mine = create(as_elena, seed, account_id=str(seed.elena_personal.id), name="Gimnasio")
        assert mine.status_code == 201
        pid = mine.json()["payment"]["id"]
        assert as_raul.get("/api/v1/schedule").json() == []
        assert (
            as_raul.put(f"/api/v1/schedule/{pid}", json=body(seed, name="Mío")).status_code == 404
        )
        assert as_raul.delete(f"/api/v1/schedule/{pid}").status_code == 404
        assert len(as_elena.get("/api/v1/schedule").json()) == 1

    def test_the_partner_cannot_undo_it_either(self, as_raul, as_elena, seed) -> None:
        made = create(as_elena, seed, account_id=str(seed.elena_personal.id), name="Gimnasio")
        undone = as_raul.post(f"/api/v1/changes/{made.json()['operation_id']}/undo")
        assert undone.status_code in (403, 404) or undone.json()["applied"] == 0
        assert len(as_elena.get("/api/v1/schedule").json()) == 1

    def test_other_households_see_nothing_and_cannot_touch_it(self, as_raul, as_ana, seed) -> None:
        pid = create(as_raul, seed).json()["payment"]["id"]
        assert as_ana.get("/api/v1/schedule").json() == []
        assert as_ana.delete(f"/api/v1/schedule/{pid}").status_code == 404
        assert create(as_ana, seed).status_code == 404  # la cuenta no es suya

    def test_anonymous_gets_401(self, client) -> None:
        assert client.get("/api/v1/schedule").status_code == 401
