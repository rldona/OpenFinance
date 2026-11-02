"""OF-1202: previsión de saldo, tipos de cuenta y privacidad."""

from datetime import timedelta

from openfinance.infrastructure.time import local_today

TODAY = local_today()


def day(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def schedule(client, account_id, amount, days_ahead, name="Pago", **kw):
    r = client.post(
        "/api/v1/schedule",
        json={
            "name": name,
            "amount": amount,
            "account_id": str(account_id),
            "frequency": "once",
            "first_due": day(days_ahead),
            **kw,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["payment"]


def forecast(client, days=60):
    r = client.get("/api/v1/forecast", params={"days": days})
    assert r.status_code == 200, r.text
    return r.json()


def by_name(view):
    return {a["name"]: a for a in view["accounts"]}


class TestForecast:
    def test_without_payments_every_account_keeps_its_balance(self, as_raul, seed) -> None:
        view = forecast(as_raul)
        accounts = by_name(view)
        assert set(accounts) == {"Cuenta conjunta", "Bankinter Raúl"}
        joint = accounts["Cuenta conjunta"]
        assert joint["start"] == joint["end"] and joint["first_negative"] is None
        assert len(joint["points"]) == 1
        [total] = view["totals"]
        assert total["currency"] == "EUR" and total["account_id"] is None

    def test_a_pending_payment_moves_the_balance_on_its_day(self, as_raul, seed) -> None:
        start = by_name(forecast(as_raul))["Cuenta conjunta"]["start"]["amount"]
        schedule(as_raul, seed.joint.id, "-50.00", 5)
        joint = by_name(forecast(as_raul))["Cuenta conjunta"]
        assert [p["day"] for p in joint["points"]] == [day(0), day(5)]
        assert float(joint["end"]["amount"]) == float(start) - 50
        assert joint["lowest"]["day"] == day(5)

    def test_the_first_negative_day_is_reported(self, as_raul, seed) -> None:
        schedule(as_raul, seed.joint.id, "-99999.00", 9, name="Entrada del piso")
        joint = by_name(forecast(as_raul))["Cuenta conjunta"]
        assert joint["first_negative"] == day(9)
        assert forecast(as_raul)["totals"][0]["first_negative"] == day(9)

    def test_payments_beyond_the_horizon_are_left_out(self, as_raul, seed) -> None:
        schedule(as_raul, seed.joint.id, "-50.00", 100)
        joint = by_name(forecast(as_raul, days=30))["Cuenta conjunta"]
        assert joint["start"] == joint["end"]

    def test_an_income_raises_the_balance(self, as_raul, seed) -> None:
        schedule(as_raul, seed.joint.id, "1600.00", 3, name="Nómina")
        joint = by_name(forecast(as_raul))["Cuenta conjunta"]
        assert float(joint["end"]["amount"]) == float(joint["start"]["amount"]) + 1600

    def test_cards_and_loans_are_not_cash(self, as_raul, seed) -> None:
        for kind in ("card", "loan"):
            r = as_raul.post(
                "/api/v1/accounts",
                json={"name": f"Mi {kind}", "type": kind, "shared": True, "opening_balance": "0"},
            )
            assert r.status_code in (200, 201), r.text
        assert set(by_name(forecast(as_raul))) == {"Cuenta conjunta", "Bankinter Raúl"}

    def test_the_forecast_never_writes_anything(self, as_raul, seed) -> None:
        schedule(as_raul, seed.joint.id, "-50.00", 5)
        before = as_raul.get("/api/v1/transactions", params={"limit": 1000}).json()
        accounts = as_raul.get("/api/v1/accounts").json()
        forecast(as_raul)
        assert as_raul.get("/api/v1/transactions", params={"limit": 1000}).json() == before
        assert as_raul.get("/api/v1/accounts").json() == accounts

    def test_the_horizon_is_bounded(self, as_raul) -> None:
        assert as_raul.get("/api/v1/forecast", params={"days": 0}).status_code == 422
        assert as_raul.get("/api/v1/forecast", params={"days": 401}).status_code == 422


class TestPrivacy:
    def test_the_partner_personal_account_is_in_neither_the_accounts_nor_the_total(
        self, as_raul, as_elena, seed
    ) -> None:
        before = forecast(as_raul)
        schedule(as_elena, seed.elena_personal.id, "-30.00", 4, name="Gimnasio")
        after = forecast(as_raul)
        assert "Bankinter Elena" not in by_name(after)
        assert after == before  # ni la cuenta, ni el pago, ni el total cambian
        hers = by_name(forecast(as_elena))["Bankinter Elena"]
        assert [p["day"] for p in hers["points"]] == [day(0), day(4)]

    def test_other_households_only_see_their_own_accounts(self, as_ana, as_raul, seed) -> None:
        schedule(as_raul, seed.joint.id, "-50.00", 5)
        view = forecast(as_ana)
        assert set(by_name(view)) == {"Su conjunta"}
        assert view["accounts"][0]["start"] == view["accounts"][0]["end"]

    def test_anonymous_gets_401(self, client) -> None:
        assert client.get("/api/v1/forecast").status_code == 401
