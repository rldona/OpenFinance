"""OF-802: «Este mes» honesto. Previsión de cierre, cuotas pendientes y cuotas fijas que no
avisan de «cerca». Hoy = 20 de octubre de 2026; el seed de conftest pone en octubre
Mercadona -87.34 (super) y Glovo -25.40."""

from datetime import date, datetime
from uuid import uuid4

import pytest

from openfinance.api.v1 import insights as insights_api
from openfinance.api.v1 import savings as savings_api
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.savings import (
    PendingCharge,
    budget_status,
    forecast_month_end,
)
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork


def eur(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "EUR"}


def slug(client, name: str) -> str:
    return next(c["id"] for c in client.get("/api/v1/categories").json() if c["slug"] == name)


@pytest.fixture(autouse=True)
def twentieth(monkeypatch):
    monkeypatch.setattr(insights_api, "local_today", lambda: date(2026, 10, 20))
    monkeypatch.setattr(savings_api, "local_today", lambda: date(2026, 10, 20))


@pytest.fixture
def add(session_factory, seed):
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


@pytest.fixture
def fixed_charges(add, seed):
    """Netflix el 5 (ya cobrada en octubre), Gimnasio el 25 (pendiente) y Seguro el 10
    (debería haber llegado y no ha llegado)."""
    for month in (6, 7, 8, 9):
        add(seed.joint, month, 5, "Netflix", "-12.99")
        add(seed.joint, month, 25, "Gimnasio", "-30.00")
        add(seed.joint, month, 10, "Seguro hogar", "-45.00")
    add(seed.joint, 10, 5, "Netflix", "-12.99")


class TestForecast:
    def test_lists_pending_charges_and_forecasts_the_close(self, as_raul, fixed_charges) -> None:
        o = as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        pending = {p["merchant"].lower(): p for p in o["pending_charges"]}
        assert set(pending) == {"gimnasio", "seguro hogar"}
        assert pending["gimnasio"]["expected_day"] == 25
        assert pending["gimnasio"]["late"] is False
        assert pending["seguro hogar"]["late"] is True
        # Lo gastado 125.73 (87.34 + 25.40 + 12.99); variable 112.74 en 20 días, 11 por delante;
        # más el gimnasio (30) y sin sumar el seguro, que no ha llegado.
        assert o["spent"] == eur("125.73")
        assert o["forecast"] == eur("217.74")

    def test_a_charge_already_paid_is_not_pending(self, as_raul, fixed_charges, add, seed) -> None:
        add(seed.joint, 10, 18, "Gimnasio", "-30.00")
        o = as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert [p["merchant"].lower() for p in o["pending_charges"]] == ["seguro hogar"]

    def test_closed_months_have_no_forecast(self, as_raul, fixed_charges) -> None:
        o = as_raul.get("/api/v1/insights/month", params={"month": "2026-09"}).json()
        assert o["forecast"] is None
        assert o["pending_charges"] == []

    def test_too_few_days_to_forecast(self, as_raul, monkeypatch) -> None:
        monkeypatch.setattr(insights_api, "local_today", lambda: date(2026, 10, 4))
        o = as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert o["forecast"] is None

    def test_my_view_never_lists_the_partners_charges(self, as_elena, as_raul, add, seed) -> None:
        for month in (6, 7, 8, 9):
            add(seed.raul_personal, month, 25, "Spotify", "-10.99")
        mine = as_raul.get(
            "/api/v1/insights/month", params={"month": "2026-10", "view": "mine"}
        ).json()
        theirs = as_elena.get(
            "/api/v1/insights/month", params={"month": "2026-10", "view": "mine"}
        ).json()
        assert [p["merchant"].lower() for p in mine["pending_charges"]] == ["spotify"]
        assert theirs["pending_charges"] == []
        shared = as_elena.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert shared["pending_charges"] == []

    def test_other_households_do_not_leak(self, as_ana, fixed_charges) -> None:
        o = as_ana.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
        assert o["pending_charges"] == []

    def test_pure_forecast_ignores_late_charges_and_refunds(self) -> None:
        eur_ = "EUR"
        late = PendingCharge("seguro", None, Money.of("45", eur_), 10, late=True)
        soon = PendingCharge("gimnasio", None, Money.of("30", eur_), 25, late=False)
        value = forecast_month_end(
            Money.of("100", eur_), Money.of("0", eur_), [late, soon], 10, 30, eur_
        )
        assert value == Money.of("100", eur_) + Money.of("30", eur_) + Money.of("200", eur_)
        # Un mes de devoluciones: el ritmo variable no puede ser negativo.
        refunds = forecast_month_end(Money.of("-20", eur_), Money.of("0", eur_), [], 10, 30, eur_)
        assert refunds == Money.of("-20", eur_)


class TestBudgetsWithFixedCharges:
    def test_a_fixed_charge_alone_does_not_say_near(self, as_raul, fixed_charges, seed) -> None:
        ocio = slug(as_raul, "suscripciones")
        # Netflix (12.99) y el gimnasio pendiente (30) son fijos: nada variable ha gastado.
        # Se recategorizan en la categoría del presupuesto.
        txns = as_raul.get(
            "/api/v1/transactions", params={"q": "netflix", "month": "2026-10"}
        ).json()
        as_raul.patch(f"/api/v1/transactions/{txns[0]['id']}", json={"category_id": ocio})
        as_raul.put(f"/api/v1/budgets/{ocio}", json={"amount": "15"})
        item = as_raul.get("/api/v1/budgets", params={"month": "2026-10"}).json()["items"][0]
        assert item["spent"] == eur("12.99")
        assert item["percent"] == 86
        assert item["status"] == "ok"

    def test_variable_spending_still_warns(self) -> None:
        limit = Money.of("100", "EUR")
        fixed = Money.of("40", "EUR")
        # 40 de cuotas + 51 variables = 91; el margen variable es 60 y se lleva el 85 %.
        assert budget_status(Money.of("91", "EUR"), limit, fixed)[1].value == "warning"
        # 40 de cuotas + 10 variables: lejos del margen.
        assert budget_status(Money.of("50", "EUR"), limit, fixed)[1].value == "ok"
        # Pasarse sigue avisando siempre.
        assert budget_status(Money.of("101", "EUR"), limit, fixed)[1].value == "over"
        # Sin cuotas, todo igual que antes.
        assert budget_status(Money.of("85", "EUR"), limit)[1].value == "warning"

    def test_fixed_charges_that_use_the_whole_budget_do_not_warn_until_exceeded(self) -> None:
        limit = Money.of("50", "EUR")
        fixed = Money.of("50", "EUR")
        assert budget_status(Money.of("50", "EUR"), limit, fixed)[1].value == "ok"
        assert budget_status(Money.of("50.01", "EUR"), limit, fixed)[1].value == "over"
