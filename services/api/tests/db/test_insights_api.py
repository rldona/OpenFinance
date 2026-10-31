"""OF-301: datos de los gráficos. Cifras calculadas a mano a partir del seed de conftest.

Conjunta: sep 28 Mercadona -60 (super) · oct 1 aportación Raúl +1600 · oct 2 hucha -300 ·
oct 3 Mercadona -87.34 (super) · oct 7 Glovo -25.40 (sin categoría).
Personales (no cuentan para el hogar): Raúl -1600 aportación, Elena -42 peluquería.
"""

from datetime import date

import pytest

from openfinance.api.v1 import insights as insights_api


@pytest.fixture(autouse=True)
def november(monkeypatch):
    """Hoy = 15 de noviembre de 2026: octubre está completo."""
    monkeypatch.setattr(insights_api, "local_today", lambda: date(2026, 11, 15))


def eur(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "EUR"}


def super_id(client) -> str:
    return next(c["id"] for c in client.get("/api/v1/categories").json() if c["slug"] == "super")


class TestMonth:
    def test_october(self, as_raul) -> None:
        o = as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert o["has_data"] is True
        assert o["spent"] == eur("112.74")
        assert o["inflow"] == eur("1600.00")
        assert o["saved"] == eur("1487.26")
        assert o["saved_to_savings"] == eur("300.00")
        assert o["saving_rate"] == 93
        assert o["previous_spent"] == eur("60.00")
        assert o["average_spent"] == eur("60.00")  # solo septiembre tiene datos antes

    def test_categories_with_their_average(self, as_raul) -> None:
        o = as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert o["categories"] == [
            {"category_id": super_id(as_raul), "amount": eur("87.34"), "average": eur("60.00")},
            {"category_id": None, "amount": eur("25.40"), "average": eur("0.00")},
        ]

    def test_daily_cumulative_spending(self, as_raul) -> None:
        o = as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert len(o["daily"]) == 31
        assert o["daily"][:3] == ["0.00", "0.00", "87.34"]
        assert o["daily"][6] == o["daily"][-1] == "112.74"
        assert len(o["previous_daily"]) == 30
        assert o["previous_daily"][27] == "60.00"

    def test_contributions_by_member(self, as_raul, seed) -> None:
        o = as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert o["contributions"] == [{"member_id": str(seed.raul.id), "amount": eur("1600.00")}]

    def test_personal_accounts_never_count(self, as_raul, as_elena) -> None:
        params = {"month": "2026-10"}
        raul = as_raul.get("/api/v1/insights/month", params=params).json()
        elena = as_elena.get("/api/v1/insights/month", params=params).json()
        assert raul == elena

    def test_month_without_data(self, as_raul) -> None:
        o = as_raul.get("/api/v1/insights/month", params={"month": "2026-08"}).json()
        assert o["has_data"] is False
        assert o["spent"] == eur("0.00")
        assert o["previous_spent"] is None
        assert o["average_spent"] is None
        assert o["saving_rate"] is None
        assert o["previous_daily"] == []

    def test_other_household_only_sees_its_own(self, as_ana) -> None:
        o = as_ana.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert o["spent"] == eur("10.00")

    def test_invalid_month(self, as_raul) -> None:
        for bad in ("2026-13", "0000-01", "1899-12"):
            r = as_raul.get("/api/v1/insights/month", params={"month": bad})
            assert r.status_code == 422, bad
        r = as_raul.get("/api/v1/transactions", params={"month": "0000-01"})
        assert r.status_code == 422

    def test_month_in_progress_is_compared_to_the_same_days(self, as_raul, monkeypatch) -> None:
        monkeypatch.setattr(insights_api, "local_today", lambda: date(2026, 10, 5))
        o = as_raul.get("/api/v1/insights/month").json()
        assert o["month"] == "2026-10"
        assert o["is_partial"] is True
        assert o["days_elapsed"] == 5
        assert o["daily"] == ["0.00", "0.00", "87.34", "87.34", "87.34"]
        assert o["previous_spent"] == eur("60.00")
        assert o["previous_spent_to_date"] == eur("0.00")  # a 5 de septiembre aún no se gastaba

    def test_complete_month_is_not_partial(self, as_raul) -> None:
        o = as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert (o["is_partial"], o["days_elapsed"]) == (False, 31)
        assert o["previous_spent_to_date"] == eur("60.00")

    def test_requires_session(self, client, seed) -> None:
        assert client.get("/api/v1/insights/month").status_code == 401


class TestCategory:
    def test_twelve_months_average_and_merchants(self, as_raul) -> None:
        d = as_raul.get(
            "/api/v1/insights/category",
            params={"month": "2026-10", "category_id": super_id(as_raul)},
        ).json()
        assert [m["month"] for m in d["months"]][:1] == ["2025-11"]
        assert d["months"][-1] == {"month": "2026-10", "amount": eur("87.34"), "has_data": True}
        assert d["months"][-2] == {"month": "2026-09", "amount": eur("60.00"), "has_data": True}
        assert d["months"][0]["has_data"] is False
        assert d["average"] == eur("60.00")
        assert d["merchants"] == [{"merchant": "Mercadona", "amount": eur("147.34"), "count": 2}]

    def test_uncategorized(self, as_raul) -> None:
        d = as_raul.get("/api/v1/insights/category", params={"month": "2026-10"}).json()
        assert d["category_id"] is None
        assert d["months"][-1]["amount"] == eur("25.40")
        assert d["merchants"][0]["merchant"] == "Glovo Dto"

    def test_category_of_another_household(self, as_raul, as_ana) -> None:
        theirs = super_id(as_ana)
        r = as_raul.get("/api/v1/insights/category", params={"category_id": theirs})
        assert r.status_code == 404

    def test_category_movements_use_only_shared_accounts(self, as_raul) -> None:
        rows = as_raul.get("/api/v1/transactions", params={"month": "2026-10"}).json()
        assert "Aportación casa" in {r["description"] for r in rows}  # su cuenta personal
        shared = as_raul.get(
            "/api/v1/transactions", params={"month": "2026-10", "shared_only": "true"}
        ).json()
        assert "Aportación casa" not in {r["description"] for r in shared}

    def test_transactions_can_be_filtered_by_category(self, as_raul) -> None:
        rows = as_raul.get(
            "/api/v1/transactions", params={"month": "2026-10", "category_id": super_id(as_raul)}
        ).json()
        assert [r["description"] for r in rows] == ["Mercadona"]


class TestTrends:
    def test_twelve_months(self, as_raul) -> None:
        t = as_raul.get("/api/v1/insights/trends", params={"month": "2026-10"}).json()
        assert len(t["months"]) == 12
        assert [m["has_data"] for m in t["months"]].count(True) == 2
        assert t["total_spent"] == eur("172.74")
        assert t["total_inflow"] == eur("1600.00")
        assert t["total_saved"] == eur("1427.26")
        assert t["average_spent"] == eur("86.37")
        assert t["average_saved"] == eur("713.63")
        assert t["saving_rate"] == 89
        assert t["best"] == {"month": "2026-10", "saved": eur("1487.26")}
        assert t["worst"] == {"month": "2026-09", "saved": eur("-60.00")}
        oct_ = t["months"][-1]
        assert {c["category_id"]: c["amount"] for c in oct_["categories"]} == {
            super_id(as_raul): eur("87.34"),
            None: eur("25.40"),
        }

    def test_months_parameter(self, as_raul) -> None:
        t = as_raul.get("/api/v1/insights/trends", params={"month": "2026-10", "months": 3}).json()
        assert [m["month"] for m in t["months"]] == ["2026-08", "2026-09", "2026-10"]
        assert as_raul.get("/api/v1/insights/trends", params={"months": 100}).status_code == 422
