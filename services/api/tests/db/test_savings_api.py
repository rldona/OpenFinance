"""Fase 4: presupuestos (OF-401), objetivos (OF-402), cuotas (OF-403) e ideas (OF-404).

Hoy = 15 de noviembre de 2026. Seed de conftest en la conjunta: sep Mercadona -60 (super),
oct Mercadona -87.34 (super), oct Glovo -25.40 (sin categoría), oct aportación +1600,
oct hucha -300. Cuentas personales aparte (nunca cuentan).
"""

from datetime import date, datetime
from uuid import uuid4

import pytest

from openfinance.api.v1 import savings as savings_api
from openfinance.domain.categories import CategoryId
from openfinance.domain.ledger import (
    Account,
    AccountKind,
    Institution,
    Transaction,
    TransactionKind,
)
from openfinance.domain.savings import Goal, GoalId
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId
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
                    category_id=category,
                )
            )
            uow.commit()

    return _add


class TestBudgets:
    def test_spent_percent_and_status(self, as_raul) -> None:
        super_ = slug(as_raul, "super")
        r = as_raul.put(f"/api/v1/budgets/{super_}", json={"amount": "100"})
        assert r.status_code == 200
        oct_ = as_raul.get("/api/v1/budgets", params={"month": "2026-10"}).json()
        assert oct_["items"] == [
            {
                "category_id": super_,
                "amount": eur("100.00"),
                "spent": eur("87.34"),
                "percent": 87,
                "status": "warning",
            }
        ]
        sep = as_raul.get("/api/v1/budgets", params={"month": "2026-09"}).json()["items"][0]
        assert (sep["spent"], sep["percent"], sep["status"]) == (eur("60.00"), 60, "ok")

    def test_only_that_category_and_month_count(self, as_raul) -> None:
        rest = slug(as_raul, "restaurantes")
        as_raul.put(f"/api/v1/budgets/{rest}", json={"amount": "50,5"})
        item = as_raul.get("/api/v1/budgets", params={"month": "2026-10"}).json()["items"][0]
        assert item["amount"] == eur("50.50")
        assert item["spent"] == eur("0.00")  # Glovo no tiene categoría

    def test_over_budget_and_totals(self, as_raul) -> None:
        as_raul.put(f"/api/v1/budgets/{slug(as_raul, 'super')}", json={"amount": "80"})
        as_raul.put(f"/api/v1/budgets/{slug(as_raul, 'ocio')}", json={"amount": "20"})
        body = as_raul.get("/api/v1/budgets", params={"month": "2026-10"}).json()
        assert body["items"][0]["status"] == "over"
        assert (body["total_amount"], body["total_spent"]) == (eur("100.00"), eur("87.34"))

    def test_update_and_delete(self, as_raul) -> None:
        super_ = slug(as_raul, "super")
        as_raul.put(f"/api/v1/budgets/{super_}", json={"amount": "100"})
        as_raul.put(f"/api/v1/budgets/{super_}", json={"amount": "200"})
        assert as_raul.get("/api/v1/budgets").json()["items"][0]["amount"] == eur("200.00")
        assert as_raul.delete(f"/api/v1/budgets/{super_}").status_code == 204
        assert as_raul.get("/api/v1/budgets").json() == {
            "month": "2026-11",
            "items": [],
            "total_amount": None,
            "total_spent": None,
        }

    @pytest.mark.parametrize("amount", ["0", "abc", "-5", "1.234"])
    def test_invalid_amounts(self, as_raul, amount) -> None:
        r = as_raul.put(f"/api/v1/budgets/{slug(as_raul, 'super')}", json={"amount": amount})
        assert r.status_code == 422

    def test_isolation(self, as_raul, as_ana) -> None:
        theirs = slug(as_ana, "super")
        assert as_raul.put(f"/api/v1/budgets/{theirs}", json={"amount": "10"}).status_code == 404
        as_ana.put(f"/api/v1/budgets/{theirs}", json={"amount": "10"})
        assert as_raul.get("/api/v1/budgets").json()["items"] == []


class TestGoals:
    def create(self, client, **extra):
        body = {"name": "Vacaciones", "icon": "🏖️", "target": "1000", "monthly": "100",
                "saved": "250", "deadline": "2027-06"} | extra  # fmt: skip
        return client.post("/api/v1/goals", json=body)

    def test_projection(self, as_raul) -> None:
        r = self.create(as_raul)
        assert r.status_code == 201
        g = r.json()
        assert g["remaining"] == eur("750.00")
        assert g["progress"] == 25
        assert g["months_to_go"] == 8  # 750 / 100 = 7,5
        assert g["eta"] == "2027-07"
        assert g["needed_monthly"] == eur("107.15")  # 750 / 7 meses, hacia arriba
        assert g["on_track"] is False

    def test_update_and_clear_deadline(self, as_raul) -> None:
        gid = self.create(as_raul).json()["id"]
        g = as_raul.patch(f"/api/v1/goals/{gid}", json={"monthly": "150"}).json()
        assert (g["eta"], g["on_track"]) == ("2027-04", True)
        g = as_raul.patch(f"/api/v1/goals/{gid}", json={"deadline": ""}).json()
        assert (g["deadline"], g["needed_monthly"], g["on_track"]) == (None, None, None)

    def test_saved_from_a_savings_account(self, as_raul, seed, session_factory) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            hucha = Account(
                AccountId(uuid4()), seed.joint.household_id, "Hucha", Institution.REVOLUT,
                AccountKind.SAVINGS, seed.joint.currency, Money.of("400.00", "EUR"),
            )  # fmt: skip
            uow.accounts.add(hucha)
            uow.commit()
        g = self.create(as_raul, account_id=str(hucha.id)).json()
        assert g["saved"] == eur("400.00")
        assert g["progress"] == 40

    def test_only_savings_accounts_can_be_linked(self, as_raul, seed) -> None:
        r = self.create(as_raul, account_id=str(seed.joint.id))
        assert r.status_code == 422

    @pytest.mark.parametrize(
        "bad", [{"target": "0"}, {"target": "x"}, {"deadline": "2027-13"}, {"name": ""}]
    )
    def test_validation(self, as_raul, bad) -> None:
        assert self.create(as_raul, **bad).status_code == 422

    def test_isolation_and_delete(self, as_raul, as_ana) -> None:
        gid = self.create(as_raul).json()["id"]
        assert as_ana.patch(f"/api/v1/goals/{gid}", json={"name": "X"}).status_code == 404
        assert as_ana.delete(f"/api/v1/goals/{gid}").status_code == 404
        assert as_ana.get("/api/v1/goals").json() == []
        assert as_raul.delete(f"/api/v1/goals/{gid}").status_code == 204
        assert as_raul.get("/api/v1/goals").json() == []


class TestOverview:
    @pytest.fixture
    def netflix(self, as_raul, seed, add):
        subs = slug(as_raul, "suscripciones")

        for month, amount in ((7, "-13.99"), (8, "-13.99"), (9, "-17.99"), (10, "-17.99")):
            add(
                seed.joint,
                month,
                12,
                "NETFLIX.COM",
                amount,
                CategoryId(__import__("uuid").UUID(subs)),
            )
            add(seed.raul_personal, month, 2, "GIMNASIO PERSONAL", "-40.00")

    def test_recurring_ideas_and_averages(self, as_raul, netflix) -> None:
        o = as_raul.get("/api/v1/savings/overview").json()
        assert o["month"] == "2026-11"
        # julio empieza el día 12 (incompleto) y noviembre está en curso: no cuentan
        assert o["months"] == ["2026-08", "2026-09", "2026-10"]
        (netflix,) = o["recurring"]  # el gimnasio es de una cuenta personal: no cuenta
        assert netflix["merchant"] == "Netflix"
        assert (netflix["first_amount"], netflix["amount"]) == (eur("13.99"), eur("17.99"))
        assert netflix["changes"] == [
            {"month": "2026-09", "before": eur("13.99"), "after": eur("17.99")}
        ]
        assert o["recurring_total"] == eur("17.99")
        ideas = {i["id"]: i for i in o["ideas"]}
        assert ideas["price-increases"]["yearly_saving"] == eur("48.00")
        assert ideas["subscriptions"]["yearly_saving"] == eur("215.88")
        assert ideas["cut-super"]["yearly_saving"] == eur("58.93")  # 49,11 x 10 % x 12
        # (-13.99 - 77.99 + 1469.27) / 3
        assert o["average_saved"] == eur("459.10")
        averages = {a["category_id"]: a["average"] for a in o["averages"]}
        assert averages[slug(as_raul, "super")] == eur("49.11")

    def test_partner_sees_the_same_household_numbers(self, as_raul, as_elena, netflix) -> None:
        a = as_raul.get("/api/v1/savings/overview").json()
        b = as_elena.get("/api/v1/savings/overview").json()
        assert a == b

    def test_only_partial_months_give_no_projections(self, as_raul, monkeypatch) -> None:
        # Hoy = 20 de octubre: septiembre empieza el 28 (incompleto) y octubre está en curso.
        monkeypatch.setattr(savings_api, "local_today", lambda: date(2026, 10, 20))
        o = as_raul.get("/api/v1/savings/overview").json()
        assert (o["months"], o["average_saved"], o["averages"], o["ideas"]) == ([], None, [], [])

    def test_installment_in_progress_does_not_fake_a_price_drop(self, as_raul, seed, add) -> None:
        for month in (7, 8, 9, 10):
            add(seed.joint, month, 2, "GIMNASIO FIT", "-39.90")
            add(seed.joint, month, 3, "GIMNASIO FIT", "-39.90")
        add(seed.joint, 11, 2, "GIMNASIO FIT", "-39.90")  # noviembre: solo el primer cargo
        (gym,) = as_raul.get("/api/v1/savings/overview").json()["recurring"]
        assert gym["amount"] == eur("79.80")
        assert gym["changes"] == []

    def test_cannot_link_a_goal_to_foreign_or_personal_accounts(
        self, as_raul, as_ana, seed
    ) -> None:
        gid = as_raul.post("/api/v1/goals", json={"name": "X", "target": "100"}).json()["id"]
        for account in (seed.other_joint.id, seed.raul_personal.id, seed.elena_personal.id):
            r = as_raul.patch(f"/api/v1/goals/{gid}", json={"account_id": str(account)})
            assert r.status_code == 422, account

    @pytest.mark.parametrize("owner", ["raul", "elena"])
    def test_goal_never_shows_the_balance_of_a_personal_account(
        self, as_raul, as_elena, seed, session_factory, owner
    ) -> None:
        """Datos antiguos con un objetivo vinculado a una cuenta personal (ADR-0013): nadie ve
        su saldo, ni siquiera su titular; se muestra lo anotado a mano."""
        personal = seed.raul_personal if owner == "raul" else seed.elena_personal
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            uow.goals.add(
                Goal(
                    id=GoalId(uuid4()),
                    household_id=seed.joint.household_id,
                    name="Antiguo",
                    icon="🎯",
                    target=Money.of("5000", "EUR"),
                    monthly=Money.of("0", "EUR"),
                    saved=Money.of("12.34", "EUR"),
                    account_id=personal.id,
                )
            )
            uow.commit()
        for client in (as_raul, as_elena):
            (goal,) = client.get("/api/v1/goals").json()
            assert goal["saved"] == eur("12.34")
            (goal,) = client.get("/api/v1/savings/overview").json()["goals"]
            assert goal["saved"] == eur("12.34")

    def test_empty_household(self, as_ana) -> None:
        o = as_ana.get("/api/v1/savings/overview").json()
        assert o["recurring"] == [] and o["goals"] == []
