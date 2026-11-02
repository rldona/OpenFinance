"""OF-1008: varias monedas con tipos de cambio manuales (ADR-0019)."""

# ruff: noqa: DTZ001  (la hora local del banco no lleva zona)
from datetime import date, datetime
from uuid import UUID, uuid4

import pytest

from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from tests.db.test_links_api import add as add_eur
from tests.db.test_links_api import link


def usd_account(client, name: str = "Viajes USD", *, shared: bool = True, opening: str = "0"):
    r = client.post(
        "/api/v1/accounts",
        json={
            "name": name,
            "type": "cash",
            "shared": shared,
            "opening_balance": opening,
            "currency": "usd",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def add_usd(
    session_factory,
    seed,
    account_id: str,
    amount: str,
    when: datetime,
    kind=TransactionKind.EXPENSE,
) -> str:
    tid = TransactionId(uuid4())
    with session_factory() as s:
        SqlUnitOfWork(s).transactions.add(
            Transaction(
                id=tid,
                household_id=seed.joint.household_id,
                account_id=AccountId(UUID(account_id)),
                booked_at=when,
                value_date=when.date(),
                description="Compra en dólares",
                amount=Money.of(amount, "USD"),
                kind=kind,
            )
        )
        s.commit()
    return str(tid)


def set_rate(client, currency: str, on: str, rate: str):
    return client.put("/api/v1/exchange-rates", json={"currency": currency, "on": on, "rate": rate})


def spent(client) -> float:
    return float(
        client.get("/api/v1/insights/month", params={"month": "2026-10"}).json()["spent"]["amount"]
    )


@pytest.fixture
def usd(as_raul, session_factory, seed):
    account = usd_account(as_raul)
    add_usd(session_factory, seed, account["id"], "-10.00", datetime(2026, 10, 12, 10))
    add_usd(session_factory, seed, account["id"], "-20.00", datetime(2026, 10, 20, 10))
    return account


class TestAccounts:
    def test_an_account_has_its_own_currency_and_balance(self, as_raul, seed) -> None:
        account = usd_account(as_raul, opening="100.50")
        assert account["balance"] == {"amount": "100.50", "currency": "USD"}
        listed = {a["name"]: a for a in as_raul.get("/api/v1/accounts").json()}
        assert listed["Viajes USD"]["balance"]["currency"] == "USD"
        assert listed["Cuenta conjunta"]["balance"]["currency"] == "EUR"

    @pytest.mark.parametrize("code", ["EU", "EURO", "12A", ""])
    def test_rejects_a_bad_currency_code(self, as_raul, seed, code) -> None:
        r = as_raul.post(
            "/api/v1/accounts",
            json={
                "name": "X",
                "type": "cash",
                "shared": True,
                "opening_balance": "0",
                "currency": code,
            },
        )
        assert r.status_code == 422


class TestReports:
    def test_without_a_rate_foreign_movements_stay_out_and_the_report_says_so(
        self, as_raul, seed, usd
    ) -> None:
        baseline = spent(as_raul)
        missing = as_raul.get("/api/v1/exchange-rates/missing").json()
        assert missing == [{"currency": "USD", "count": 2, "first": "2026-10-12"}]
        assert baseline == 112.74  # solo lo de euros: el dólar no se inventa

    def test_with_a_rate_they_count_converted(self, as_raul, seed, usd) -> None:
        assert set_rate(as_raul, "USD", "2026-10-01", "0.90").status_code == 200
        assert spent(as_raul) == pytest.approx(112.74 + 27.00)
        assert as_raul.get("/api/v1/exchange-rates/missing").json() == []

    def test_the_rate_of_the_day_or_the_latest_before_applies(self, as_raul, seed, usd) -> None:
        set_rate(as_raul, "USD", "2026-10-15", "1.00")
        # El gasto del día 12 es anterior al tipo: sigue sin convertir; el del 20 usa el del 15.
        assert spent(as_raul) == pytest.approx(112.74 + 20.00)
        assert as_raul.get("/api/v1/exchange-rates/missing").json()[0]["count"] == 1
        set_rate(as_raul, "USD", "2026-10-18", "2.00")
        assert spent(as_raul) == pytest.approx(112.74 + 40.00)

    def test_rounds_once_at_the_end_half_even(self, as_raul, seed, session_factory) -> None:
        account = usd_account(as_raul, "Un dólar")
        add_usd(session_factory, seed, account["id"], "-10.00", datetime(2026, 10, 12, 10))
        set_rate(as_raul, "USD", "2026-10-01", "1.23456789")
        assert spent(as_raul) == pytest.approx(112.74 + 12.35)

    def test_a_single_currency_household_is_unchanged(self, as_raul, seed) -> None:
        assert spent(as_raul) == 112.74
        assert as_raul.get("/api/v1/exchange-rates/missing").json() == []

    def test_balances_stay_in_the_accounts_currency(self, as_raul, seed, usd) -> None:
        set_rate(as_raul, "USD", "2026-10-01", "0.90")
        listed = {a["name"]: a for a in as_raul.get("/api/v1/accounts").json()}
        assert listed["Viajes USD"]["balance"] == {"amount": "-30.00", "currency": "USD"}

    def test_the_movements_total_does_not_mix_currencies(self, as_raul, seed, usd) -> None:
        page = as_raul.get("/api/v1/transactions/page", params={"month": "2026-10"}).json()
        assert page["other_currencies"] == ["USD"]
        assert page["total"]["currency"] == "EUR"
        everything = as_raul.get("/api/v1/transactions", params={"month": "2026-10"}).json()
        expected = sum(
            float(t["amount"]["amount"]) for t in everything if t["amount"]["currency"] == "EUR"
        )
        assert float(page["total"]["amount"]) == pytest.approx(expected)


class TestRates:
    def test_set_list_correct_and_delete_with_undo(self, as_raul, seed) -> None:
        r = set_rate(as_raul, "usd", "2026-10-01", "0,9")
        assert r.status_code == 200 and r.json()["rate"]["rate"] == "0.90000000"
        op1 = r.json()["operation_id"]
        op2 = set_rate(as_raul, "USD", "2026-10-01", "0.95").json()["operation_id"]
        assert set_rate(as_raul, "USD", "2026-10-01", "0.95").json()["operation_id"] is None
        assert as_raul.get("/api/v1/exchange-rates").json()[0]["rate"] == "0.95000000"
        assert as_raul.post(f"/api/v1/changes/{op2}/undo").json()["applied"] == 1
        assert as_raul.get("/api/v1/exchange-rates").json()[0]["rate"] == "0.90000000"
        assert as_raul.post(f"/api/v1/changes/{op1}/undo").status_code == 200
        assert as_raul.get("/api/v1/exchange-rates").json() == []
        assert as_raul.post(f"/api/v1/changes/{op1}/redo").status_code == 200
        deleted = as_raul.delete("/api/v1/exchange-rates/USD/2026-10-01").json()["operation_id"]
        assert as_raul.get("/api/v1/exchange-rates").json() == []
        assert as_raul.post(f"/api/v1/changes/{deleted}/undo").status_code == 200
        assert len(as_raul.get("/api/v1/exchange-rates").json()) == 1
        assert as_raul.delete("/api/v1/exchange-rates/GBP/2026-10-01").status_code == 404

    @pytest.mark.parametrize(
        ("currency", "on", "rate"),
        [
            ("EUR", "2026-10-01", "1"),  # la moneda del hogar no necesita tipo
            ("USD", "2999-01-01", "1"),  # futuro
            ("USD", "2026-10-01", "0"),
            ("USD", "2026-10-01", "1.123456789"),  # 9 decimales
            ("US1", "2026-10-01", "1"),
            ("USD", "2026-10-01", "mucho"),
        ],
    )
    def test_invalid_rates_are_422(self, as_raul, seed, currency, on, rate) -> None:
        assert set_rate(as_raul, currency, on, rate).status_code == 422
        assert as_raul.get("/api/v1/exchange-rates").json() == []

    def test_rates_are_per_household(self, as_raul, as_ana, seed) -> None:
        set_rate(as_raul, "USD", "2026-10-01", "0.9")
        assert as_ana.get("/api/v1/exchange-rates").json() == []

    def test_the_partners_undo_is_404_and_a_session_is_required(
        self, as_raul, as_elena, client, seed
    ) -> None:
        op = set_rate(as_raul, "USD", "2026-10-01", "0.9").json()["operation_id"]
        assert as_elena.post(f"/api/v1/changes/{op}/undo").status_code == 404
        assert client.get("/api/v1/exchange-rates").status_code == 401


class TestPrivacy:
    def test_missing_rates_only_count_what_you_see(
        self, as_raul, as_elena, session_factory, seed
    ) -> None:
        mine = usd_account(as_elena, "USD de Elena", shared=False)
        add_usd(session_factory, seed, mine["id"], "-5.00", datetime(2026, 10, 3, 10))
        assert as_raul.get("/api/v1/exchange-rates/missing").json() == []
        assert as_elena.get("/api/v1/exchange-rates/missing").json()[0]["count"] == 1

    def test_foreign_personal_movements_stay_out_of_my_reports(
        self, as_raul, as_elena, session_factory, seed
    ) -> None:
        mine = usd_account(as_elena, "USD de Elena", shared=False)
        add_usd(session_factory, seed, mine["id"], "-500.00", datetime(2026, 10, 3, 10))
        set_rate(as_elena, "USD", "2026-10-01", "1")
        assert spent(as_raul) == 112.74


class TestLinks:
    def test_a_transfer_between_currencies_keeps_both_real_amounts(
        self, as_raul, session_factory, seed
    ) -> None:
        account = usd_account(as_raul, "Tarjeta USD")
        usd_side = add_usd(
            session_factory,
            seed,
            account["id"],
            "55.00",
            datetime(2026, 10, 10, 9),
            TransactionKind.INCOME,
        )
        eur_side = add_eur(
            session_factory, seed.joint, "Cambio de divisa", "-50.00", datetime(2026, 10, 10, 8)
        )
        r = link(as_raul, eur_side, usd_side)
        assert r.status_code == 200
        assert r.json()["transaction"]["amount"] == {"amount": "-50.00", "currency": "EUR"}
        assert r.json()["peer"]["amount"] == {"amount": "55.00", "currency": "USD"}

    def test_same_signs_are_still_rejected(self, as_raul, session_factory, seed) -> None:
        account = usd_account(as_raul, "Tarjeta USD")
        a = add_usd(session_factory, seed, account["id"], "-55.00", datetime(2026, 10, 10, 9))
        b = add_eur(session_factory, seed.joint, "Gasto", "-50.00", datetime(2026, 10, 10, 8))
        assert link(as_raul, b, a).status_code == 422

    def test_date_is_str(self) -> None:
        assert date(2026, 10, 1).isoformat() == "2026-10-01"


def test_the_export_carries_rates_and_account_types(as_raul, seed, usd) -> None:
    set_rate(as_raul, "USD", "2026-10-01", "0.9")
    data = as_raul.get("/api/v1/export", params={"format": "json"}).json()
    assert data["exchange_rates"] == [
        {"currency": "USD", "on": "2026-10-01", "rate": "0.90000000", "source": "manual"}
    ]
    accounts = {a["name"]: a for a in data["accounts"]}
    assert (accounts["Viajes USD"]["currency"], accounts["Viajes USD"]["type"]) == ("USD", "cash")
    assert accounts["Cuenta conjunta"]["type"] == "bank"
