"""OF-1203: sobres con arrastre e importes por mes (ADR-0022).

Hoy = 15 de noviembre de 2026. Seed de conftest en la conjunta (categoría «super»): sep -60,
oct -87,34. Las cuentas personales no cuentan nunca.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

import pytest

from openfinance.api.v1 import savings as savings_api
from openfinance.domain.categories import CategoryId
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork


@pytest.fixture(autouse=True)
def november(monkeypatch):
    monkeypatch.setattr(savings_api, "local_today", lambda: date(2026, 11, 15))


def eur(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "EUR"}


def slug(client, name: str) -> str:
    return next(c["id"] for c in client.get("/api/v1/categories").json() if c["slug"] == name)


@pytest.fixture
def add(session_factory):
    def _add(account, month, day, desc, amount, category=None):
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            uow.transactions.add(
                Transaction(
                    id=TransactionId(uuid4()),
                    household_id=account.household_id,
                    account_id=account.id,
                    booked_at=datetime(2026, month, day, 12),  # noqa: DTZ001
                    value_date=date(2026, month, day),
                    description=desc,
                    amount=Money.of(amount, "EUR"),
                    kind=TransactionKind.EXPENSE,
                    category_id=CategoryId(UUID(category)) if category else None,
                )
            )
            uow.commit()

    return _add


def envelope(client, category, amount="100", started="2026-09"):
    r = client.put(
        f"/api/v1/budgets/{category}",
        json={"amount": amount, "mode": "envelope", "started": started},
    )
    assert r.status_code == 200, r.text
    return r.json()


def month(client, category, m):
    items = client.get("/api/v1/budgets", params={"month": m}).json()["items"]
    return next(i for i in items if i["category_id"] == category)


class TestCarry:
    def test_what_is_left_passes_to_the_next_month(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        envelope(as_raul, sup)
        sep, oct_, nov = (month(as_raul, sup, m) for m in ("2026-09", "2026-10", "2026-11"))
        assert (sep["carried"], sep["available"]) == (eur("0.00"), eur("40.00"))
        assert (oct_["carried"], oct_["available"]) == (eur("40.00"), eur("52.66"))
        assert (nov["carried"], nov["available"]) == (eur("52.66"), eur("152.66"))
        assert oct_["amount"] == eur("100.00") and oct_["mode"] == "envelope"
        assert oct_["started"] == "2026-09"

    def test_a_deficit_carries_and_makes_the_envelope_over(self, as_raul, seed, add) -> None:
        sup = slug(as_raul, "super")
        add(seed.joint, 9, 20, "Mercadona grande", "-300.00", category=sup)
        envelope(as_raul, sup)
        oct_ = month(as_raul, sup, "2026-10")
        assert oct_["carried"] == eur("-260.00")  # 100 - 360
        assert oct_["available"] == eur("-247.34")
        assert oct_["status"] == "over"

    def test_before_the_start_nothing_carries(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        envelope(as_raul, sup, started="2026-10")
        assert month(as_raul, sup, "2026-09")["carried"] == eur("0.00")
        assert month(as_raul, sup, "2026-10")["carried"] == eur("0.00")
        assert month(as_raul, sup, "2026-11")["carried"] == eur("12.66")

    def test_correcting_an_old_movement_corrects_later_months(self, as_raul, seed, add) -> None:
        sup = slug(as_raul, "super")
        envelope(as_raul, sup)
        before = month(as_raul, sup, "2026-11")["carried"]
        add(seed.joint, 9, 25, "Otro", "-10.00", category=sup)
        after = month(as_raul, sup, "2026-11")["carried"]
        assert (before, after) == (eur("52.66"), eur("42.66"))

    def test_the_default_start_is_this_month(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        r = as_raul.put(f"/api/v1/budgets/{sup}", json={"amount": "100", "mode": "envelope"})
        assert r.json()["started"] == "2026-11"

    def test_an_existing_envelope_keeps_its_start_when_edited(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        envelope(as_raul, sup, started="2026-09")
        r = as_raul.put(f"/api/v1/budgets/{sup}", json={"amount": "120", "mode": "envelope"})
        assert r.json()["started"] == "2026-09"

    def test_back_to_a_limit_stops_carrying(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        envelope(as_raul, sup)
        as_raul.put(f"/api/v1/budgets/{sup}", json={"amount": "100"})
        item = month(as_raul, sup, "2026-11")
        assert (item["mode"], item["carried"], item["started"]) == ("limit", eur("0.00"), None)

    def test_a_limit_ignores_what_was_left_over(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        as_raul.put(f"/api/v1/budgets/{sup}", json={"amount": "100"})
        assert month(as_raul, sup, "2026-11")["available"] == eur("100.00")

    def test_totals_use_what_can_be_spent(self, as_raul) -> None:
        envelope(as_raul, slug(as_raul, "super"))
        body = as_raul.get("/api/v1/budgets", params={"month": "2026-10"}).json()
        assert (body["total_amount"], body["total_spent"]) == (eur("140.00"), eur("87.34"))


class TestMonthAmounts:
    def test_one_month_can_have_its_own_amount(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        envelope(as_raul, sup)
        r = as_raul.put(f"/api/v1/budgets/{sup}/months/2026-10", json={"amount": "200"})
        assert r.status_code == 200, r.text
        oct_ = r.json()
        assert (oct_["amount"], oct_["base_amount"], oct_["has_override"]) == (
            eur("200.00"),
            eur("100.00"),
            True,
        )
        assert month(as_raul, sup, "2026-09")["has_override"] is False
        # y lo que sobra pasa al mes siguiente: 40 + 200 - 87,34 = 152,66
        assert month(as_raul, sup, "2026-11")["carried"] == eur("152.66")

    def test_it_also_works_in_a_plain_limit(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        as_raul.put(f"/api/v1/budgets/{sup}", json={"amount": "100"})
        as_raul.put(f"/api/v1/budgets/{sup}/months/2026-10", json={"amount": "80"})
        item = month(as_raul, sup, "2026-10")
        assert (item["amount"], item["status"]) == (eur("80.00"), "over")
        assert month(as_raul, sup, "2026-09")["amount"] == eur("100.00")

    def test_removing_it_goes_back_to_the_base(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        envelope(as_raul, sup)
        as_raul.put(f"/api/v1/budgets/{sup}/months/2026-10", json={"amount": "200"})
        assert as_raul.delete(f"/api/v1/budgets/{sup}/months/2026-10").status_code == 204
        assert month(as_raul, sup, "2026-10")["has_override"] is False

    def test_deleting_the_budget_deletes_its_months(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        envelope(as_raul, sup)
        as_raul.put(f"/api/v1/budgets/{sup}/months/2026-10", json={"amount": "200"})
        as_raul.delete(f"/api/v1/budgets/{sup}")
        as_raul.put(f"/api/v1/budgets/{sup}", json={"amount": "100"})
        assert month(as_raul, sup, "2026-10")["has_override"] is False

    def test_validation(self, as_raul) -> None:
        sup = slug(as_raul, "super")
        # sin presupuesto no hay a qué ponerle un mes
        assert (
            as_raul.put(f"/api/v1/budgets/{sup}/months/2026-10", json={"amount": "5"}).status_code
            == 404
        )
        envelope(as_raul, sup)
        for bad in ("0", "-5", "mucho"):
            assert (
                as_raul.put(
                    f"/api/v1/budgets/{sup}/months/2026-10", json={"amount": bad}
                ).status_code
                == 422
            )
        assert (
            as_raul.put(f"/api/v1/budgets/{sup}/months/2026-13", json={"amount": "5"}).status_code
            == 422
        )
        future = as_raul.put(
            f"/api/v1/budgets/{sup}", json={"amount": "5", "mode": "envelope", "started": "2027-01"}
        )
        assert future.status_code == 422


class TestPrivacy:
    def test_personal_accounts_never_count_toward_an_envelope(
        self, as_raul, as_elena, seed, add
    ) -> None:
        sup = slug(as_raul, "super")
        envelope(as_raul, sup)
        before = month(as_raul, sup, "2026-11")
        add(seed.raul_personal, 10, 5, "Compra mía", "-500.00", category=sup)
        add(seed.elena_personal, 9, 5, "Compra suya", "-500.00", category=sup)
        assert month(as_raul, sup, "2026-11") == before
        assert month(as_elena, sup, "2026-11") == before  # el sobre es del hogar

    def test_other_households_cannot_touch_it(self, as_raul, as_ana) -> None:
        sup = slug(as_raul, "super")
        envelope(as_raul, sup)
        assert as_ana.get("/api/v1/budgets", params={"month": "2026-10"}).json()["items"] == []
        assert (
            as_ana.put(f"/api/v1/budgets/{sup}/months/2026-10", json={"amount": "1"}).status_code
            == 404
        )
        assert as_ana.delete(f"/api/v1/budgets/{sup}/months/2026-10").status_code == 404
        assert month(as_raul, sup, "2026-10")["has_override"] is False

    def test_anonymous_gets_401(self, client) -> None:
        sup = "00000000-0000-0000-0000-000000000000"
        assert (
            client.put(f"/api/v1/budgets/{sup}/months/2026-10", json={"amount": "1"}).status_code
            == 401
        )
