"""OF-1301: avisos deterministas, descartarlos y privacidad."""

from datetime import timedelta

from openfinance.infrastructure.time import local_today

TODAY = local_today()


def spend(client, account, description, amount, days_ago=0):
    r = client.post(
        "/api/v1/transactions",
        json={
            "booked_on": (TODAY - timedelta(days=days_ago)).isoformat(),
            "description": description,
            "amount": amount.lstrip("-"),
            "kind": "expense",
            "account_id": str(account.id),
        },
    )
    assert r.status_code == 201, r.text


def kinds(client):
    return [a["kind"] for a in client.get("/api/v1/alerts").json()]


def fee_keys(client):
    """El seed deja la cuenta de Raúl en negativo: se mira solo lo que cada test provoca."""
    return [a["key"] for a in client.get("/api/v1/alerts").json() if a["kind"] == "fee"]


class TestDetectors:
    def test_a_duplicate_charge_is_flagged_once(self, as_raul, seed) -> None:
        spend(as_raul, seed.joint, "Cine Kinepolis", "-18.50", 1)
        spend(as_raul, seed.joint, "Cine Kinepolis", "-18.50", 0)
        found = as_raul.get("/api/v1/alerts").json()
        dup = [a for a in found if a["kind"] == "duplicate"]
        assert len(dup) == 1
        assert dup[0]["amount"] == {"amount": "18.50", "currency": "EUR"}
        assert dup[0]["account_id"] == str(seed.joint.id)

    def test_the_same_charge_far_apart_or_with_another_amount_is_not(self, as_raul, seed) -> None:
        spend(as_raul, seed.joint, "Cine Kinepolis", "-18.50", 6)
        spend(as_raul, seed.joint, "Cine Kinepolis", "-18.50", 0)
        spend(as_raul, seed.joint, "Cafetería", "-3.00", 1)
        spend(as_raul, seed.joint, "Cafetería", "-3.10", 0)
        assert "duplicate" not in kinds(as_raul)

    def test_a_fee_is_flagged_by_its_description(self, as_raul, seed) -> None:
        spend(as_raul, seed.joint, "Comisión de mantenimiento", "-2.00", 3)
        spend(as_raul, seed.joint, "Mercadona", "-20.00", 3)
        fee = [a for a in as_raul.get("/api/v1/alerts").json() if a["kind"] == "fee"]
        assert [a["severity"] for a in fee] == ["info"]
        assert fee[0]["title"] == "Comisión: Comisión de mantenimiento"

    def test_a_late_payment_is_flagged(self, as_raul, seed) -> None:
        r = as_raul.post(
            "/api/v1/schedule",
            json={
                "name": "Gimnasio",
                "amount": "-30.00",
                "account_id": str(seed.joint.id),
                "frequency": "monthly",
                "first_due": (TODAY - timedelta(days=12)).isoformat(),
            },
        )
        assert r.status_code == 201, r.text
        late = [a for a in as_raul.get("/api/v1/alerts").json() if a["kind"] == "late_payment"]
        assert [a["title"] for a in late] == ["Gimnasio no ha llegado"]

    def test_a_forecast_below_zero_is_critical_and_first(self, as_raul, seed) -> None:
        as_raul.post(
            "/api/v1/schedule",
            json={
                "name": "Seguro",
                "amount": "-5000.00",
                "account_id": str(seed.joint.id),
                "frequency": "once",
                "first_due": (TODAY + timedelta(days=4)).isoformat(),
            },
        )
        spend(as_raul, seed.joint, "Comisión", "-1.00", 2)
        found = as_raul.get("/api/v1/alerts").json()
        assert found[0]["kind"] == "low_balance" and found[0]["severity"] == "critical"
        assert found[0]["on"] == (TODAY + timedelta(days=4)).isoformat()

    def test_an_exceeded_budget_is_flagged(self, as_raul, seed) -> None:
        cat = next(c for c in as_raul.get("/api/v1/categories").json() if c["slug"] == "ocio")
        assert (
            as_raul.put(f"/api/v1/budgets/{cat['id']}", json={"amount": "10.00"}).status_code < 300
        )
        r = as_raul.post(
            "/api/v1/transactions",
            json={
                "booked_on": TODAY.isoformat(),
                "description": "Teatro",
                "amount": "40.00",
                "kind": "expense",
                "account_id": str(seed.joint.id),
                "category_id": cat["id"],
            },
        )
        assert r.status_code == 201, r.text
        over = [a for a in as_raul.get("/api/v1/alerts").json() if a["kind"] == "budget_over"]
        assert len(over) == 1 and over[0]["amount"]["amount"] == "30.00"


class TestDismiss:
    def test_dismissing_hides_it_only_for_that_person(self, as_raul, as_elena, seed) -> None:
        spend(as_raul, seed.joint, "Comisión", "-2.00", 1)
        (key,) = fee_keys(as_raul)
        assert as_raul.post("/api/v1/alerts/dismiss", json={"key": key}).status_code == 204
        assert fee_keys(as_raul) == []
        assert fee_keys(as_elena) == [key]

    def test_dismissing_twice_is_fine(self, as_raul, seed) -> None:
        spend(as_raul, seed.joint, "Comisión", "-2.00", 1)
        (key,) = fee_keys(as_raul)
        for _ in range(2):
            assert as_raul.post("/api/v1/alerts/dismiss", json={"key": key}).status_code == 204

    def test_an_invented_key_is_not_found(self, as_raul) -> None:
        assert as_raul.post("/api/v1/alerts/dismiss", json={"key": "fee:nope"}).status_code == 404

    def test_writes_need_the_requested_with_header(self, as_raul) -> None:
        as_raul.headers.pop("X-Requested-With", None)
        assert as_raul.post("/api/v1/alerts/dismiss", json={"key": "x"}).status_code == 403

    def test_requires_login(self, client) -> None:
        assert client.get("/api/v1/alerts").status_code == 401


class TestPrivacy:
    def test_a_personal_account_alert_is_only_for_its_owner(self, as_raul, as_elena, seed) -> None:
        spend(as_elena, seed.elena_personal, "Comisión de tarjeta", "-9.00", 1)
        assert len(fee_keys(as_elena)) == 1
        assert fee_keys(as_raul) == []

    def test_nobody_can_dismiss_an_alert_they_cannot_see(self, as_raul, as_elena, seed) -> None:
        spend(as_elena, seed.elena_personal, "Comisión de tarjeta", "-9.00", 1)
        (key,) = fee_keys(as_elena)
        assert as_raul.post("/api/v1/alerts/dismiss", json={"key": key}).status_code == 404
        assert fee_keys(as_elena) == [key]

    def test_another_household_sees_nothing(self, as_raul, as_ana, seed) -> None:
        spend(as_raul, seed.joint, "Comisión", "-2.00", 1)
        assert fee_keys(as_ana) == []
