"""OF-1005: efectivo, tarjeta, préstamo e inversión (solo seguimiento)."""

# ruff: noqa: DTZ001  (la hora local del banco no lleva zona)
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork


def create(client, name: str, type_: str, *, shared: bool = True, opening: str = "0"):
    return client.post(
        "/api/v1/accounts",
        json={"name": name, "type": type_, "shared": shared, "opening_balance": opening},
    )


def names(client) -> dict[str, dict]:
    return {a["name"]: a for a in client.get("/api/v1/accounts").json()}


def add_expense(session_factory, seed, account_id: str, amount: str) -> None:
    with session_factory() as s:
        SqlUnitOfWork(s).transactions.add(
            Transaction(
                id=TransactionId(uuid4()),
                household_id=seed.joint.household_id,
                account_id=AccountId(UUID(account_id)),
                booked_at=datetime(2026, 10, 15, 12),
                value_date=datetime(2026, 10, 15).date(),
                description="Compra de prueba",
                amount=Money.of(amount, "EUR"),
                kind=TransactionKind.EXPENSE,
            )
        )
        s.commit()


def spent(client) -> str:
    return client.get("/api/v1/insights/month", params={"month": "2026-10"}).json()["spent"][
        "amount"
    ]


class TestCreate:
    def test_existing_accounts_are_bank_accounts(self, as_raul, seed) -> None:
        assert {a["type"] for a in as_raul.get("/api/v1/accounts").json()} == {"bank"}

    @pytest.mark.parametrize("type_", ["cash", "card", "loan", "investment"])
    def test_creates_each_type(self, as_raul, seed, type_) -> None:
        r = create(as_raul, f"Mi {type_}", type_, opening="100.00")
        assert r.status_code == 201
        assert r.json()["type"] == type_
        assert r.json()["balance"]["amount"] == "100.00"
        assert names(as_raul)[f"Mi {type_}"]["type"] == type_

    def test_a_debt_is_a_negative_balance(self, as_raul, seed) -> None:
        r = create(as_raul, "Hipoteca", "loan", opening="-150000.50")
        assert r.status_code == 201
        assert names(as_raul)["Hipoteca"]["balance"]["amount"] == "-150000.50"

    def test_shared_is_seen_by_both_and_personal_only_by_its_owner(
        self, as_raul, as_elena, seed
    ) -> None:
        create(as_raul, "Efectivo casa", "cash", shared=True)
        create(as_raul, "Mi tarjeta", "card", shared=False)
        assert {"Efectivo casa"} <= set(names(as_elena))
        assert "Mi tarjeta" not in names(as_elena)
        assert names(as_raul)["Mi tarjeta"]["kind"] == "personal"
        assert names(as_raul)["Mi tarjeta"]["owner_id"] == str(seed.raul.id)

    def test_bank_accounts_are_not_created_from_the_web(self, as_raul, seed) -> None:
        assert create(as_raul, "Otro banco", "bank").status_code == 422

    def test_duplicate_names_are_a_conflict(self, as_raul, seed) -> None:
        assert create(as_raul, "Efectivo", "cash").status_code == 201
        assert create(as_raul, "efectivo", "cash").status_code == 409
        assert create(as_raul, "CUENTA CONJUNTA", "cash").status_code == 409

    @pytest.mark.parametrize("opening", ["abc", "1.234", "1e3", ""])
    def test_invalid_opening_balance_is_422(self, as_raul, seed, opening) -> None:
        assert create(as_raul, "X", "cash", opening=opening).status_code == 422

    def test_other_households_do_not_see_it(self, as_raul, as_ana, seed) -> None:
        create(as_raul, "Efectivo", "cash")
        assert "Efectivo" not in names(as_ana)

    def test_requires_a_session(self, client, seed) -> None:
        assert create(client, "X", "cash").status_code == 401


class TestReports:
    def test_loans_and_investments_do_not_count_as_spending(
        self, as_raul, session_factory, seed
    ) -> None:
        before = spent(as_raul)
        for type_ in ("loan", "investment"):
            account = create(as_raul, f"Cuenta {type_}", type_).json()
            add_expense(session_factory, seed, account["id"], "-500.00")
        assert spent(as_raul) == before

    def test_cash_and_card_purchases_are_spending(self, as_raul, session_factory, seed) -> None:
        before = float(spent(as_raul))
        cash = create(as_raul, "Efectivo", "cash").json()
        card = create(as_raul, "Visa", "card").json()
        add_expense(session_factory, seed, cash["id"], "-10.00")
        add_expense(session_factory, seed, card["id"], "-40.00")
        assert float(spent(as_raul)) == before + 50

    def test_the_balance_of_a_card_is_what_is_owed(self, as_raul, session_factory, seed) -> None:
        card = create(as_raul, "Visa", "card").json()
        add_expense(session_factory, seed, card["id"], "-40.00")
        assert names(as_raul)["Visa"]["balance"]["amount"] == "-40.00"

    def test_their_movements_are_still_listed(self, as_raul, session_factory, seed) -> None:
        loan = create(as_raul, "Hipoteca", "loan").json()
        add_expense(session_factory, seed, loan["id"], "-500.00")
        rows = as_raul.get("/api/v1/transactions", params={"account_id": loan["id"]}).json()
        assert [t["description"] for t in rows] == ["Compra de prueba"]
