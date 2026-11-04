"""OF-1204: plantillas de movimientos, uso por el alta manual y privacidad."""

from datetime import timedelta

from openfinance.infrastructure.time import local_today

TODAY = local_today()


def body(seed, **kw):
    return {
        "name": "Café de la oficina",
        "kind": "expense",
        "amount": "1.80",
        "description": "Café",
        "account_id": str(seed.joint.id),
        **kw,
    }


def create(client, seed, **kw):
    return client.post("/api/v1/templates", json=body(seed, **kw))


def names(client):
    return [t["name"] for t in client.get("/api/v1/templates").json()]


class TestCrud:
    def test_create_list_update_delete_with_undo_and_redo(self, as_raul, seed) -> None:
        r = create(as_raul, seed, tags=["trabajo"])
        assert r.status_code == 201, r.text
        template = r.json()["template"]
        assert template["amount"] == {"amount": "1.80", "currency": "EUR"}
        assert template["tags"] == ["trabajo"] and template["personal"] is False
        assert names(as_raul) == ["Café de la oficina"]

        up = as_raul.put(
            f"/api/v1/templates/{template['id']}", json=body(seed, name="Café", amount="2")
        )
        assert up.status_code == 200 and up.json()["template"]["amount"]["amount"] == "2.00"
        undo = as_raul.post(f"/api/v1/changes/{up.json()['operation_id']}/undo")
        assert undo.json()["applied"] == 1 and names(as_raul) == ["Café de la oficina"]

        gone = as_raul.delete(f"/api/v1/templates/{template['id']}").json()["operation_id"]
        assert names(as_raul) == []
        assert as_raul.post(f"/api/v1/changes/{gone}/undo").status_code == 200
        assert names(as_raul) == ["Café de la oficina"]
        made = r.json()["operation_id"]
        assert as_raul.post(f"/api/v1/changes/{made}/undo").json()["applied"] == 1
        assert names(as_raul) == []
        assert as_raul.post(f"/api/v1/changes/{made}/redo").json()["applied"] == 1
        assert names(as_raul) == ["Café de la oficina"]

    def test_an_unchanged_update_leaves_no_trace(self, as_raul, seed) -> None:
        template = create(as_raul, seed).json()["template"]
        r = as_raul.put(f"/api/v1/templates/{template['id']}", json=body(seed, amount="1,8"))
        assert r.status_code == 200 and r.json()["operation_id"] is None

    def test_rejects_what_makes_no_sense(self, as_raul, seed) -> None:
        for bad in (
            {"amount": "0"},
            {"amount": "1.234"},
            {"kind": "savings_transfer"},
            {"kind": "income", "category_id": str(seed.joint.id)},
            {"tags": ["a|b"]},
        ):
            assert create(as_raul, seed, **bad).status_code in (404, 422), bad
        ghost = "00000000-0000-0000-0000-000000000000"
        assert create(as_raul, seed, category_id=ghost).status_code == 404
        assert create(as_raul, seed, account_id=ghost).status_code == 404

    def test_a_name_is_not_repeated(self, as_raul, seed) -> None:
        assert create(as_raul, seed).status_code == 201
        assert create(as_raul, seed, name="café DE LA oficina").status_code == 409


class TestUse:
    def test_creates_an_expense_with_the_template_data(self, as_raul, seed) -> None:
        cats = {c["slug"]: c["id"] for c in as_raul.get("/api/v1/categories").json()}
        tid = create(
            as_raul, seed, category_id=cats["restaurantes"], tags=["trabajo"], note="con leche"
        ).json()["template"]["id"]
        r = as_raul.post(f"/api/v1/templates/{tid}/use", json={})
        assert r.status_code == 201, r.text
        t = r.json()["transaction"]
        assert t["amount"] == {"amount": "-1.80", "currency": "EUR"}
        assert (t["description"], t["category_id"], t["note"]) == (
            "Café",
            cats["restaurantes"],
            "con leche",
        )
        assert t["booked_at"][:10] == TODAY.isoformat() and t["source"] == "manual"
        assert t["tags"] == ["trabajo"]

    def test_an_income_is_positive_and_the_date_can_be_chosen(self, as_raul, seed) -> None:
        tid = create(as_raul, seed, kind="income", amount="50", name="Venta").json()["template"][
            "id"
        ]
        day = (TODAY - timedelta(days=3)).isoformat()
        t = as_raul.post(f"/api/v1/templates/{tid}/use", json={"booked_on": day}).json()
        assert t["transaction"]["amount"]["amount"] == "50.00"
        assert t["transaction"]["booked_at"][:10] == day

    def test_undoing_the_use_voids_the_movement(self, as_raul, seed) -> None:
        tid = create(as_raul, seed).json()["template"]["id"]
        used = as_raul.post(f"/api/v1/templates/{tid}/use", json={}).json()
        tx = used["transaction"]["id"]
        assert as_raul.post(f"/api/v1/changes/{used['operation_id']}/undo").json()["applied"] == 1
        listed = [
            t["id"] for t in as_raul.get("/api/v1/transactions", params={"limit": 1000}).json()
        ]
        assert tx not in listed
        assert len(as_raul.get("/api/v1/templates").json()) == 1  # la plantilla sigue

    def test_using_it_twice_makes_two_movements(self, as_raul, seed) -> None:
        tid = create(as_raul, seed).json()["template"]["id"]
        a = as_raul.post(f"/api/v1/templates/{tid}/use", json={}).json()["transaction"]["id"]
        b = as_raul.post(f"/api/v1/templates/{tid}/use", json={}).json()["transaction"]["id"]
        assert a != b


class TestPrivacy:
    def test_a_household_template_cannot_use_a_personal_account(self, as_raul, seed) -> None:
        r = create(as_raul, seed, account_id=str(seed.raul_personal.id))
        assert r.status_code == 422
        assert (
            create(as_raul, seed, account_id=str(seed.raul_personal.id), personal=True).status_code
            == 201
        )

    def test_the_partner_cannot_use_my_account_in_a_template(self, as_raul, as_elena, seed) -> None:
        r = create(as_elena, seed, account_id=str(seed.raul_personal.id), personal=True)
        assert r.status_code == 404

    def test_a_personal_template_is_invisible_to_the_partner_in_every_way(
        self, as_raul, as_elena, seed
    ) -> None:
        made = create(
            as_raul, seed, account_id=str(seed.raul_personal.id), personal=True, name="Mía"
        )
        tid = made.json()["template"]["id"]
        assert names(as_elena) == [] and names(as_raul) == ["Mía"]
        assert (
            as_elena.put(f"/api/v1/templates/{tid}", json=body(seed, name="Suya")).status_code
            == 404
        )
        assert as_elena.delete(f"/api/v1/templates/{tid}").status_code == 404
        assert as_elena.post(f"/api/v1/templates/{tid}/use", json={}).status_code == 404
        assert names(as_raul) == ["Mía"]

    def test_the_partner_cannot_undo_it_either(self, as_raul, as_elena, seed) -> None:
        made = create(as_raul, seed, account_id=str(seed.raul_personal.id), personal=True)
        undone = as_elena.post(f"/api/v1/changes/{made.json()['operation_id']}/undo")
        assert undone.status_code in (403, 404) or undone.json()["applied"] == 0
        assert names(as_raul) == ["Café de la oficina"]

    def test_a_household_template_is_shared(self, as_raul, as_elena, seed) -> None:
        tid = create(as_raul, seed).json()["template"]["id"]
        assert names(as_elena) == ["Café de la oficina"]
        r = as_elena.post(f"/api/v1/templates/{tid}/use", json={})
        assert r.status_code == 201

    def test_other_households_see_nothing_and_cannot_touch_it(self, as_raul, as_ana, seed) -> None:
        tid = create(as_raul, seed).json()["template"]["id"]
        assert names(as_ana) == []
        assert as_ana.delete(f"/api/v1/templates/{tid}").status_code == 404
        assert as_ana.post(f"/api/v1/templates/{tid}/use", json={}).status_code == 404
        assert create(as_ana, seed).status_code == 404  # la cuenta no es suya

    def test_anonymous_gets_401(self, client) -> None:
        assert client.get("/api/v1/templates").status_code == 401
