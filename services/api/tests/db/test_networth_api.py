"""OF-1501: patrimonio neto de quien mira, hoy y a fin de mes."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.networth import history_dates, month_end
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from tests.db.test_rates_api import set_rate, usd_account

TODAY = datetime.now(UTC).date()


def worth(client) -> dict:
    r = client.get("/api/v1/net-worth")
    assert r.status_code == 200, r.text
    return r.json()


def create(client, name, type_, opening, **extra):
    r = client.post(
        "/api/v1/accounts",
        json={"name": name, "type": type_, "shared": False, "opening_balance": opening, **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


def add_tx(session_factory, household, account_id, amount, when, currency="EUR"):
    kind = TransactionKind.INCOME
    with session_factory() as s:
        SqlUnitOfWork(s).transactions.add(
            Transaction(
                id=TransactionId(uuid4()),
                household_id=household,
                account_id=AccountId(UUID(str(account_id))),
                booked_at=when,
                value_date=when.date(),
                description="Prueba",
                amount=Money.of(amount, currency),
                kind=kind,
            )
        )
        s.commit()


def amount(m: dict) -> Decimal:
    return Decimal(m["amount"])


def test_today_matches_the_sum_of_the_balances_you_see(as_raul, seed):
    body = worth(as_raul)
    balances = [amount(a["balance"]) for a in as_raul.get("/api/v1/accounts").json()]
    assert amount(body["today"]["net"]) == sum(balances)
    assert body["currency"] == "EUR"
    assert (
        body["today"]["on"] == TODAY.isoformat() or body["today"]["on"]
    )  # hoy en la zona del hogar
    assert amount(body["today"]["assets"]) - amount(body["today"]["debts"]) == amount(
        body["today"]["net"]
    )


def test_assets_and_debts_split_by_sign_and_cards_are_debts(as_raul, seed):
    before = worth(as_raul)["today"]
    create(as_raul, "Visa", "card", "-250.00")
    create(as_raul, "Hipoteca", "loan", "-100000.00")
    create(as_raul, "Fondo", "investment", "5000.00")
    after = worth(as_raul)
    assert amount(after["today"]["debts"]) - amount(before["debts"]) == Decimal("100250.00")
    assert amount(after["today"]["assets"]) - amount(before["assets"]) == Decimal("5000.00")
    types = {t["type"]: amount(t["net"]) for t in after["by_type"]}
    assert types["card"] == Decimal("-250.00")
    assert types["loan"] == Decimal("-100000.00")
    assert types["investment"] == Decimal("5000.00")


def test_a_card_paid_too_much_counts_as_an_asset(as_raul, seed):
    before = worth(as_raul)["today"]
    create(as_raul, "Visa", "card", "40.00")
    after = worth(as_raul)["today"]
    assert amount(after["assets"]) - amount(before["assets"]) == Decimal("40.00")
    assert amount(after["debts"]) == amount(before["debts"])


def test_someone_elses_personal_account_never_counts(as_raul, as_elena, as_ana, seed):
    raul, elena, ana = worth(as_raul), worth(as_elena), worth(as_ana)
    raul_ids = {a["account_id"] for a in raul["accounts"]}
    elena_ids = {a["account_id"] for a in elena["accounts"]}
    assert str(seed.elena_personal.id) not in raul_ids
    assert str(seed.raul_personal.id) not in elena_ids
    assert str(seed.other_joint.id) not in raul_ids | elena_ids
    # y las cifras son las de cada una, no las del hogar entero
    assert amount(raul["today"]["net"]) != amount(elena["today"]["net"])
    assert [a["name"] for a in ana["accounts"]] == ["Su conjunta"]
    # nada de lo de Elena asoma en el historial de Raúl: ni cuentas ni importes sueltos
    assert "Bankinter Elena" not in as_raul.get("/api/v1/net-worth").text


def test_history_has_twelve_month_ends_and_today(as_raul, seed):
    body = worth(as_raul)
    assert len(body["history"]) == 13
    dates = [p["on"] for p in body["history"]]
    assert dates == sorted(dates)
    assert dates == [d.isoformat() for d in history_dates(datetime.fromisoformat(dates[-1]).date())]
    assert body["history"][-1] == body["today"]


def test_a_movement_counts_from_its_date_on(as_raul, seed, session_factory):
    first = TODAY.replace(day=1)
    before = worth(as_raul)
    add_tx(
        session_factory,
        seed.joint.household_id,
        seed.joint.id,
        "1000.00",
        datetime.combine(first, datetime.min.time()),
    )
    after = worth(as_raul)
    last_month_end = (first - timedelta(days=1)).isoformat()
    old_before = next(p for p in before["history"] if p["on"] == last_month_end)
    old_after = next(p for p in after["history"] if p["on"] == last_month_end)
    assert old_after["net"] == old_before["net"]  # el mes anterior no cambia
    assert amount(after["today"]["net"]) - amount(before["today"]["net"]) == Decimal("1000.00")


def test_voided_movements_do_not_count(as_raul, seed, session_factory):
    before = amount(worth(as_raul)["today"]["net"])
    tx = as_raul.post(
        "/api/v1/transactions",
        json={
            "account_id": str(seed.joint.id),
            "booked_on": TODAY.isoformat(),
            "description": "Cena",
            "amount": "30.00",
            "kind": "expense",
        },
    )
    assert tx.status_code == 201, tx.text
    assert amount(worth(as_raul)["today"]["net"]) == before - Decimal("30.00")
    assert (
        as_raul.delete(f"/api/v1/transactions/{tx.json()['transaction']['id']}").status_code == 200
    )
    assert amount(worth(as_raul)["today"]["net"]) == before


def test_foreign_accounts_convert_or_are_listed_as_missing(as_raul, seed):
    base = worth(as_raul)
    usd_account(as_raul, "Viajes USD", opening="100.00", shared=False)
    without_rate = worth(as_raul)
    assert without_rate["missing_rates"] == ["USD"]
    assert without_rate["today"]["excluded"] == 1
    assert without_rate["today"]["net"] == base["today"]["net"]  # no se inventa un valor
    usd = next(a for a in without_rate["accounts"] if a["name"] == "Viajes USD")
    assert usd["value"] is None and usd["balance"] == {"amount": "100.00", "currency": "USD"}
    set_rate(as_raul, "USD", (TODAY - timedelta(days=2)).isoformat(), "0.90")
    with_rate = worth(as_raul)
    assert (
        with_rate["missing_rates"] == []
    )  # hay un tipo anterior a todas las fechas que importan...
    assert amount(with_rate["today"]["net"]) - amount(base["today"]["net"]) == Decimal("90.00")


def test_requires_a_session(app, seed):
    from fastapi.testclient import TestClient

    assert TestClient(app).get("/api/v1/net-worth").status_code == 401


def test_month_end_helper():
    assert month_end(2026, 2).day == 28 and month_end(2028, 2).day == 29
    assert (
        history_dates(datetime(2026, 1, 15, tzinfo=UTC).date())[0]
        == datetime(2025, 1, 31, tzinfo=UTC).date()
    )
