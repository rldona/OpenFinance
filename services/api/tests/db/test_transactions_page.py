"""OF-803: movimientos paginados por cursor, con el total del filtro."""

from datetime import datetime
from uuid import uuid4

import pytest

from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork


def eur(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "EUR"}


@pytest.fixture
def many(session_factory, seed):
    """23 gastos de 1 € en la conjunta, varios con la misma hora (empates en el orden)."""
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        for i in range(23):
            when = datetime(2026, 8, 1 + i // 3, 12)  # noqa: DTZ001 - tres por día
            uow.transactions.add(
                Transaction(
                    id=TransactionId(uuid4()),
                    household_id=seed.joint.household_id,
                    account_id=seed.joint.id,
                    booked_at=when,
                    value_date=when.date(),
                    description=f"Compra {i:02d}",
                    amount=Money.of("-1.00", "EUR"),
                    kind=TransactionKind.EXPENSE,
                )
            )
        uow.commit()


def walk(client, **params):
    pages, cursor = [], None
    while True:
        q = {**params, **({"cursor": cursor} if cursor else {})}
        r = client.get("/api/v1/transactions/page", params=q)
        assert r.status_code == 200, r.text
        pages.append(r.json())
        cursor = pages[-1]["next_cursor"]
        if not cursor:
            return pages


class TestPaging:
    def test_walking_the_cursor_returns_every_movement_once_in_order(self, as_raul, many) -> None:
        full = as_raul.get("/api/v1/transactions", params={"month": "2026-08"}).json()
        pages = walk(as_raul, month="2026-08", limit=5)
        assert [len(p["items"]) for p in pages] == [5, 5, 5, 5, 3]
        assert [t["id"] for p in pages for t in p["items"]] == [t["id"] for t in full]

    def test_total_is_for_the_whole_filter_on_every_page(self, as_raul, many) -> None:
        pages = walk(as_raul, month="2026-08", limit=10)
        assert {(p["count"], p["total"]["amount"]) for p in pages} == {(23, "-23.00")}

    def test_filters_apply_to_the_total(self, as_raul, many) -> None:
        r = as_raul.get("/api/v1/transactions/page", params={"q": "Compra 1", "limit": 3}).json()
        assert r["count"] == 10  # Compra 10 … Compra 19
        assert len(r["items"]) == 3
        assert r["next_cursor"]

    def test_last_page_has_no_cursor(self, as_raul, many) -> None:
        r = as_raul.get("/api/v1/transactions/page", params={"month": "2026-08", "limit": 23})
        assert r.json()["next_cursor"] is None

    def test_empty_filter(self, as_raul) -> None:
        r = as_raul.get("/api/v1/transactions/page", params={"q": "no existe"}).json()
        assert r == {
            "items": [],
            "next_cursor": None,
            "count": 0,
            "total": eur("0.00"),
            "other_currencies": [],
        }

    def test_invalid_cursor_and_limit(self, as_raul) -> None:
        assert as_raul.get("/api/v1/transactions/page", params={"cursor": "zzz"}).status_code == 422
        assert as_raul.get("/api/v1/transactions/page", params={"limit": 0}).status_code == 422
        assert as_raul.get("/api/v1/transactions/page", params={"limit": 201}).status_code == 422

    def test_a_voided_movement_leaves_the_total(self, as_raul, many, session_factory) -> None:
        first = as_raul.get("/api/v1/transactions/page", params={"month": "2026-08"}).json()
        gone = first["items"][0]
        # Se anula con la operación normal: un movimiento manual se puede borrar.
        created = as_raul.post(
            "/api/v1/transactions",
            json={
                "booked_on": "2026-08-30",
                "description": "Efectivo",
                "amount": "10.00",
                "kind": "expense",
                "account_id": gone["account_id"],
            },
        )
        assert created.status_code == 201, created.text
        tid = created.json()["transaction"]["id"]
        with_manual = as_raul.get("/api/v1/transactions/page", params={"month": "2026-08"}).json()
        assert with_manual["count"] == 24
        assert with_manual["total"] == eur("-33.00")
        as_raul.delete(f"/api/v1/transactions/{tid}")
        after = as_raul.get("/api/v1/transactions/page", params={"month": "2026-08"}).json()
        assert (after["count"], after["total"]) == (23, eur("-23.00"))


class TestPrivacy:
    def test_the_partner_personal_account_is_never_in_pages_or_totals(
        self, as_raul, as_elena, seed
    ) -> None:
        mine = as_raul.get("/api/v1/transactions/page", params={"q": "Peluquería"}).json()
        assert (mine["count"], mine["items"]) == (0, [])
        hers = as_elena.get("/api/v1/transactions/page", params={"q": "Peluquería"}).json()
        assert hers["count"] == 1
        assert hers["total"] == eur("-42.00")

    def test_a_cursor_does_not_open_other_accounts(self, as_raul, as_elena, many) -> None:
        cursor = as_elena.get("/api/v1/transactions/page", params={"limit": 1}).json()[
            "next_cursor"
        ]
        r = as_raul.get("/api/v1/transactions/page", params={"cursor": cursor, "limit": 200}).json()
        assert all("Peluquer" not in t["description"] for t in r["items"])

    def test_the_partner_personal_account_cannot_be_asked_for(self, as_raul, seed) -> None:
        r = as_raul.get(
            "/api/v1/transactions/page", params={"account_id": str(seed.elena_personal.id)}
        )
        assert r.status_code == 404

    def test_other_households_are_invisible(self, as_ana, as_raul, many) -> None:
        r = as_ana.get("/api/v1/transactions/page", params={"limit": 200}).json()
        assert r["count"] == 1  # solo su «Mercadona vecinos»
        assert all("Compra" not in t["description"] for t in r["items"])
        assert (
            as_ana.get("/api/v1/transactions/page", params={"account_id": str(uuid4())}).status_code
            == 404
        )

    def test_anonymous_gets_401(self, client) -> None:
        assert client.get("/api/v1/transactions/page").status_code == 401
