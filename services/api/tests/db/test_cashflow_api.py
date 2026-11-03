"""OF-1502: flujo de caja mensual del dinero líquido."""

import itertools
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from openfinance.domain.insights import Month
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from tests.db.test_rates_api import usd_account

NOW = datetime.now(UTC)
CURRENT = Month(NOW.year, NOW.month)


def flow(client, months=12):
    r = client.get("/api/v1/cash-flow", params={"months": months})
    assert r.status_code == 200, r.text
    return r.json()


def amt(m):
    return Decimal(m["amount"])


def add(session_factory, account, amount, kind, month: Month, day=10, **extra):
    when = datetime(month.year, month.month, day, 12)  # noqa: DTZ001
    with session_factory() as s:
        SqlUnitOfWork(s).transactions.add(
            Transaction(
                id=TransactionId(uuid4()),
                household_id=account.household_id,
                account_id=AccountId(account.id),
                booked_at=when,
                value_date=when.date(),
                description="Prueba",
                amount=Money.of(amount, "EUR"),
                kind=kind,
                **extra,
            )
        )
        s.commit()


def test_one_month_per_requested_count_ending_now(as_raul, seed):
    body = flow(as_raul, 6)
    assert [m["month"] for m in body["months"]] == [
        str(CURRENT.shift(-i)) for i in range(5, -1, -1)
    ]
    assert body["months"][-1]["is_partial"] is True
    assert all(not m["is_partial"] for m in body["months"][:-1])
    assert body["currency"] == "EUR"


def row(client, month: Month) -> dict:
    return next(x for x in flow(client)["months"] if x["month"] == str(month))


def delta(before: dict, after: dict, key: str) -> Decimal:
    return amt(after[key]) - amt(before[key])


def test_each_kind_lands_in_its_own_box(as_raul, seed, session_factory):
    m = CURRENT.shift(-2)
    before = row(as_raul, m)
    add(session_factory, seed.joint, "2000.00", TransactionKind.INCOME, m)
    add(session_factory, seed.joint, "-300.00", TransactionKind.EXPENSE, m)
    add(session_factory, seed.joint, "50.00", TransactionKind.EXPENSE, m, 11)  # devolución
    add(session_factory, seed.joint, "-120.00", TransactionKind.SAVINGS_TRANSFER, m)
    add(session_factory, seed.joint, "-15.00", TransactionKind.INTERNAL_TRANSFER, m)
    after = row(as_raul, m)
    assert delta(before, after, "income") == Decimal("2000.00")
    assert delta(before, after, "spending") == Decimal("250.00")  # neto de la devolución
    assert delta(before, after, "savings") == Decimal("120.00")
    assert delta(before, after, "transfers") == Decimal("-15.00")
    assert delta(before, after, "contributions") == 0


def test_the_change_of_every_month_matches_the_difference_between_balances(
    as_raul, seed, session_factory
):
    add(session_factory, seed.joint, "900.00", TransactionKind.INCOME, CURRENT.shift(-3))
    add(session_factory, seed.joint, "-70.00", TransactionKind.EXPENSE, CURRENT.shift(-3), 20)
    add(
        session_factory,
        seed.raul_personal,
        "-40.00",
        TransactionKind.SAVINGS_TRANSFER,
        CURRENT.shift(-1),
    )
    add(session_factory, seed.joint, "10.00", TransactionKind.INTERNAL_TRANSFER, CURRENT.shift(-1))
    months = flow(as_raul, 6)["months"]
    for previous, month in itertools.pairwise(months):
        assert amt(month["change"]) == amt(month["end_balance"]) - amt(previous["end_balance"])
    # y el último saldo es el que suman las cuentas líquidas que ve
    accounts = as_raul.get("/api/v1/accounts").json()
    total = sum(amt(a["balance"]) for a in accounts if a["type"] in ("bank", "cash"))
    assert amt(months[-1]["end_balance"]) == total


def test_contributions_between_my_accounts_cancel_out(as_raul, as_elena, seed, session_factory):
    m = CURRENT.shift(-1)
    mine_before, hers_before = row(as_raul, m), row(as_elena, m)
    # Raúl aporta 500 desde su cuenta personal a la conjunta
    add(
        session_factory,
        seed.joint,
        "500.00",
        TransactionKind.CONTRIBUTION,
        m,
        member_id=seed.raul.id,
    )
    add(
        session_factory, seed.raul_personal, "-500.00", TransactionKind.CONTRIBUTION, m,
        member_id=seed.raul.id,
    )  # fmt: skip
    mine, hers = row(as_raul, m), row(as_elena, m)
    assert delta(mine_before, mine, "contributions") == 0
    # Elena no ve la cuenta personal de Raúl: para ella son 500 que entran a la conjunta
    assert delta(hers_before, hers, "contributions") == Decimal("500.00")


def test_someone_elses_personal_account_never_enters(as_raul, as_elena, seed, session_factory):
    m = CURRENT.shift(-1)
    raul_before, elena_before = row(as_raul, m), row(as_elena, m)
    add(session_factory, seed.elena_personal, "-777.00", TransactionKind.EXPENSE, m)
    assert delta(raul_before, row(as_raul, m), "spending") == 0
    assert delta(elena_before, row(as_elena, m), "spending") == Decimal("777.00")
    assert "777" not in as_raul.get("/api/v1/cash-flow").text


def test_other_households_are_invisible(as_raul, as_ana, seed, session_factory):
    m = CURRENT.shift(-1)
    ana_before = row(as_ana, m)
    add(session_factory, seed.other_joint, "-5555.00", TransactionKind.EXPENSE, m)
    assert "5555" not in as_raul.get("/api/v1/cash-flow").text
    assert delta(ana_before, row(as_ana, m), "spending") == Decimal("5555.00")


def test_cards_and_loans_are_left_out(as_raul, seed, session_factory):
    from uuid import UUID

    card = as_raul.post(
        "/api/v1/accounts",
        json={"name": "Visa", "type": "card", "shared": True, "opening_balance": "0"},
    ).json()

    class Ref:
        household_id = seed.joint.household_id
        id = UUID(card["id"])

    m = CURRENT.shift(-1)
    before = row(as_raul, m)
    add(session_factory, Ref, "-99.00", TransactionKind.EXPENSE, m)
    assert row(as_raul, m) == before


def test_foreign_liquid_accounts_are_left_out_and_counted(as_raul, seed):
    base = flow(as_raul)
    usd_account(as_raul, "Viajes USD", opening="100.00", shared=False)
    body = flow(as_raul)
    assert body["excluded_foreign"] == 1
    assert body["accounts"] == base["accounts"]
    assert body["months"][-1]["end_balance"] == base["months"][-1]["end_balance"]


def test_voided_movements_do_not_count(as_raul, seed, session_factory):
    m = CURRENT.shift(-1)
    before = row(as_raul, m)
    add(session_factory, seed.joint, "-60.00", TransactionKind.EXPENSE, m, voided=True)
    assert row(as_raul, m) == before


def test_months_out_of_range_and_no_session(app, as_raul, seed):
    for bad in (0, 37):
        assert as_raul.get("/api/v1/cash-flow", params={"months": bad}).status_code == 422
    assert TestClient(app).get("/api/v1/cash-flow").status_code == 401


def test_default_is_twelve_months(as_raul, seed):
    assert len(as_raul.get("/api/v1/cash-flow").json()["months"]) == 12
    assert len(flow(as_raul, 36)["months"]) == 36
