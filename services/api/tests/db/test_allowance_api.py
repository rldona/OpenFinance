"""OF-1205: «hoy podéis gastar».

Hoy = 10 de noviembre de 2026. La conjunta del seed tiene 1227,26 € (100 de saldo inicial).
"""

from datetime import date

import pytest

from openfinance.api.v1 import savings as savings_api
from openfinance.api.v1 import schedule as schedule_api

TODAY = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(schedule_api, "local_today", lambda: TODAY)
    monkeypatch.setattr(savings_api, "local_today", lambda: TODAY)


def eur(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "EUR"}


def plan(client, account, amount, due, name="Pago", **kw):
    r = client.post(
        "/api/v1/schedule",
        json={
            "name": name,
            "amount": amount,
            "account_id": str(account.id),
            "frequency": "once",
            "first_due": due,
            **kw,
        },
    )
    assert r.status_code == 201, r.text


def allowance(client):
    r = client.get("/api/v1/allowance")
    assert r.status_code == 200, r.text
    return r.json()


class TestAllowance:
    def test_without_scheduled_payments_it_does_not_make_up_a_number(self, as_raul) -> None:
        a = allowance(as_raul)
        assert a["status"] == "no_schedule" and a["per_day"] is None and a["available"] is None

    def test_until_the_next_income(self, as_raul, seed) -> None:
        plan(as_raul, seed.joint, "-900.00", "2026-11-20", name="Alquiler")
        plan(as_raul, seed.joint, "1600.00", "2026-11-28", name="Nómina")
        a = allowance(as_raul)
        assert a["status"] == "ok" and a["horizon"] == "income" and a["until"] == "2026-11-28"
        assert (a["balance"], a["committed"], a["available"]) == (
            eur("1227.26"),
            eur("900.00"),
            eur("327.26"),
        )
        assert (a["days"], a["per_day"], a["short"]) == (18, eur("18.18"), False)
        assert [p["name"] for p in a["pending"]] == ["Alquiler"]
        assert a["next_income"]["name"] == "Nómina" and a["next_income"]["due"] == "2026-11-28"

    def test_without_an_income_it_runs_to_the_end_of_the_month(self, as_raul, seed) -> None:
        plan(as_raul, seed.joint, "-200.00", "2026-11-15", name="Seguro")
        a = allowance(as_raul)
        assert (a["horizon"], a["until"], a["days"]) == ("month_end", "2026-11-30", 21)
        assert a["next_income"] is None and a["per_day"] == eur("48.91")  # 1027,26 / 21 = 48,917…

    def test_not_enough_money_is_said_and_gives_zero(self, as_raul, seed) -> None:
        plan(as_raul, seed.joint, "-5000.00", "2026-11-12", name="Entrada del piso")
        a = allowance(as_raul)
        assert a["short"] is True and a["per_day"] == eur("0.00")
        assert a["available"] == eur("-3772.74")

    def test_what_is_late_or_after_the_horizon_does_not_count(self, as_raul, seed) -> None:
        plan(as_raul, seed.joint, "-300.00", "2026-11-05", name="Atrasado")  # ya pasó, sin cobro
        plan(as_raul, seed.joint, "-300.00", "2026-12-05", name="Del mes que viene")
        a = allowance(as_raul)
        assert a["committed"] == eur("0.00")

    def test_envelopes_show_what_is_left(self, as_raul, seed) -> None:
        plan(as_raul, seed.joint, "-200.00", "2026-11-15", name="Seguro")
        sup = next(
            c["id"] for c in as_raul.get("/api/v1/categories").json() if c["slug"] == "super"
        )
        as_raul.put(
            f"/api/v1/budgets/{sup}",
            json={"amount": "100", "mode": "envelope", "started": "2026-09"},
        )
        as_raul.put(f"/api/v1/budgets/{sup}/months/2026-11", json={"amount": "100"})
        [env] = allowance(as_raul)["envelopes"]
        assert env["category_id"] == sup and env["available"] == eur("152.66")

    def test_a_limit_is_not_an_envelope(self, as_raul, seed) -> None:
        plan(as_raul, seed.joint, "-200.00", "2026-11-15", name="Seguro")
        sup = next(
            c["id"] for c in as_raul.get("/api/v1/categories").json() if c["slug"] == "super"
        )
        as_raul.put(f"/api/v1/budgets/{sup}", json={"amount": "100"})
        assert allowance(as_raul)["envelopes"] == []


class TestPrivacy:
    def test_personal_accounts_never_count_and_both_see_the_same(
        self, as_raul, as_elena, seed
    ) -> None:
        plan(as_raul, seed.joint, "-200.00", "2026-11-15", name="Seguro")
        before = allowance(as_raul)
        plan(as_elena, seed.elena_personal, "-9000.00", "2026-11-12", name="Suyo")
        plan(as_raul, seed.raul_personal, "-8000.00", "2026-11-13", name="Mío")
        assert allowance(as_raul) == before == allowance(as_elena)

    def test_a_personal_only_schedule_is_not_enough_data(self, as_raul, seed) -> None:
        plan(as_raul, seed.raul_personal, "-8000.00", "2026-11-13", name="Mío")
        assert allowance(as_raul)["status"] == "no_schedule"

    def test_other_households_get_their_own_numbers(self, as_raul, as_ana, seed) -> None:
        plan(as_raul, seed.joint, "-200.00", "2026-11-15", name="Seguro")
        assert allowance(as_ana)["status"] == "no_schedule"
        plan(as_ana, seed.other_joint, "-10.00", "2026-11-20", name="Cuota")
        a = allowance(as_ana)
        assert a["balance"] == eur("40.00") and a["committed"] == eur("10.00")
        assert [p["name"] for p in a["pending"]] == ["Cuota"]

    def test_anonymous_gets_401(self, client) -> None:
        assert client.get("/api/v1/allowance").status_code == 401
