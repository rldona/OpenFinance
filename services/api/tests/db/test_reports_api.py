"""OF-1503: informes a medida y su guardado."""

from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from tests.db.conftest import CSRF
from tests.db.test_rates_api import usd_account

OCT = {"from_month": "2026-10", "to_month": "2026-10"}


def definition(**extra):
    return {"measure": "spent", "group_by": "category", **OCT, **extra}


def run(client, **extra):
    r = client.post("/api/v1/reports/run", json=definition(**extra))
    assert r.status_code == 200, r.text
    return r.json()


def rows(report) -> dict:
    return {r["key"]: Decimal(r["amount"]["amount"]) for r in report["rows"]}


def total(report) -> Decimal:
    return Decimal(report["total"]["amount"])


def category_id(session_factory, seed, slug="super"):
    with session_factory() as s:
        return next(
            c.id
            for c in SqlUnitOfWork(s).categories.for_household(seed.joint.household_id)
            if c.slug == slug
        )


# --- ejecutar --------------------------------------------------------------------------------


def test_spent_by_category_matches_the_ledger(as_raul, seed, session_factory):
    report = run(as_raul)
    super_id = str(category_id(session_factory, seed))
    assert rows(report) == {super_id: Decimal("87.34"), None: Decimal("25.40")}
    assert total(report) == Decimal("112.74")
    assert report["count"] == 2
    labels = {r["key"]: r["label"] for r in report["rows"]}
    assert labels[None] == "Sin categoría" and labels[super_id] == "Supermercado"


def test_group_by_month_is_chronological_and_covers_the_period(as_raul, seed):
    report = run(as_raul, from_month="2026-09", group_by="month")
    assert [r["key"] for r in report["rows"]] == ["2026-09", "2026-10"]
    assert rows(report) == {"2026-09": Decimal("60.00"), "2026-10": Decimal("112.74")}


def test_group_by_account_and_merchant(as_raul, seed):
    by_account = run(as_raul, group_by="account")
    assert rows(by_account) == {str(seed.joint.id): Decimal("112.74")}
    assert by_account["rows"][0]["label"] == "Cuenta conjunta"
    by_merchant = run(as_raul, group_by="merchant")
    assert Decimal("87.34") in rows(by_merchant).values()
    assert by_merchant["rows"][0]["label"] == "Mercadona"


def test_each_measure(as_raul, seed):
    assert total(run(as_raul, measure="saved")) == Decimal("300.00")
    assert total(run(as_raul, measure="income")) == Decimal("0.00")
    assert total(run(as_raul, measure="net")) == Decimal("-112.74")


def test_filters_by_account_category_amount_and_tags(as_raul, seed, session_factory):
    super_id = category_id(session_factory, seed)
    assert total(run(as_raul, account_ids=[str(seed.joint.id)])) == Decimal("112.74")
    assert total(run(as_raul, category_ids=[str(super_id)])) == Decimal("87.34")
    assert total(run(as_raul, category_ids=[str(super_id)], uncategorized=True)) == Decimal(
        "112.74"
    )
    assert total(run(as_raul, uncategorized=True)) == Decimal("25.40")
    assert total(run(as_raul, min_amount="50")) == Decimal("87.34")
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        glovo = next(
            t for t in uow.transactions.for_account(seed.joint.household_id, seed.joint.id)
            if t.description == "Glovo 50% dto"
        )  # fmt: skip
        uow.tags.set(seed.joint.household_id, glovo.id, ("Cena", "Viaje"))
        s.commit()
    assert total(run(as_raul, tags=["viaje"])) == Decimal("25.40")
    assert total(run(as_raul, tags=["#cena", "otra"])) == Decimal("25.40")
    assert total(run(as_raul, tags=["otra"])) == Decimal("0.00")


def test_each_person_sees_their_own_accounts(as_raul, as_elena, as_ana, seed):
    assert total(run(as_raul)) == Decimal("112.74")
    assert total(run(as_elena)) == Decimal("154.74")  # + la peluquería de su cuenta personal
    assert total(run(as_ana)) == Decimal("10.00")
    assert (
        "Peluquería"
        not in as_raul.post("/api/v1/reports/run", json=definition(group_by="merchant")).text
    )


def test_filtering_by_an_account_you_cannot_see_is_404(as_raul, as_ana, seed):
    for hidden in (seed.elena_personal.id, seed.other_joint.id, uuid4()):
        r = as_raul.post("/api/v1/reports/run", json=definition(account_ids=[str(hidden)]))
        assert r.status_code == 404, hidden
    r = as_ana.post("/api/v1/reports/run", json=definition(account_ids=[str(seed.joint.id)]))
    assert r.status_code == 404


def test_unknown_category_is_404(as_raul, seed):
    r = as_raul.post("/api/v1/reports/run", json=definition(category_ids=[str(uuid4())]))
    assert r.status_code == 404


def test_invalid_definitions_are_422(as_raul, seed):
    bad = [
        {"from_month": "2026-10", "to_month": "2026-09"},
        {"from_month": "2020-01", "to_month": "2026-10"},  # más de 36 meses
        {"measure": "everything"},
        {"group_by": "sql"},
        {"min_amount": "-1"},
        {"min_amount": "abc"},
        {"from_month": "2026-13"},
        {"tags": ["a|b"]},
        {"account_ids": ["no-es-uuid"]},
    ]
    for extra in bad:
        r = as_raul.post("/api/v1/reports/run", json=definition(**extra))
        assert r.status_code == 422, extra


def test_foreign_currency_without_rate_is_reported_and_left_out(as_raul, seed, session_factory):
    from datetime import datetime
    from uuid import UUID, uuid4

    from openfinance.domain.ledger import Transaction, TransactionKind
    from openfinance.domain.shared import Money

    usd = usd_account(as_raul, "Viajes USD", opening="0", shared=False)
    assert run(as_raul)["missing_rates"] == []
    with session_factory() as s:
        SqlUnitOfWork(s).transactions.add(
            Transaction(
                id=uuid4(),
                household_id=seed.joint.household_id,
                account_id=UUID(usd["id"]),
                booked_at=datetime(2026, 10, 12, 12),  # noqa: DTZ001
                value_date=datetime(2026, 10, 12).date(),  # noqa: DTZ001
                description="Hotel",
                amount=Money.of("-80.00", "USD"),
                kind=TransactionKind.EXPENSE,
            )
        )
        s.commit()
    report = run(as_raul)
    assert report["missing_rates"] == ["USD"]
    assert total(report) == Decimal("112.74")  # el gasto en USD sin tipo no entra


def test_csv_has_header_rows_and_total(as_raul, seed):
    r = as_raul.post(
        "/api/v1/reports/run", params={"format": "csv"}, json=definition(group_by="account")
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.content.decode("utf-8-sig").strip().split("\r\n")
    assert lines[0] == "grupo,importe,moneda,movimientos"
    assert "Cuenta conjunta,112.74,EUR,2" in lines
    assert lines[-1] == "Total,112.74,EUR,2"


def test_csv_neutralises_a_label_that_a_spreadsheet_would_run(as_raul, seed, session_factory):
    from datetime import datetime
    from uuid import uuid4

    from openfinance.domain.ledger import Transaction, TransactionKind
    from openfinance.domain.shared import Money

    with session_factory() as s:
        SqlUnitOfWork(s).transactions.add(
            Transaction(
                id=uuid4(),
                household_id=seed.joint.household_id,
                account_id=seed.joint.id,
                booked_at=datetime(2026, 10, 12, 12),  # noqa: DTZ001
                value_date=datetime(2026, 10, 12).date(),  # noqa: DTZ001
                description="Cargo raro",
                amount=Money.of("-9.00", "EUR"),
                kind=TransactionKind.EXPENSE,
                merchant="=CMD|' /C CALC'!A0",
            )
        )
        s.commit()
    r = as_raul.post(
        "/api/v1/reports/run", params={"format": "csv"}, json=definition(group_by="merchant")
    )
    text = r.content.decode("utf-8-sig")
    assert ",9.00,EUR,1" in text
    assert "\r\n=" not in text and "'=" in text


# --- guardar ---------------------------------------------------------------------------------


def save(client, name="Gasto de octubre", shared=False, **extra):
    r = client.post(
        "/api/v1/reports", json={"name": name, "shared": shared, "definition": definition(**extra)}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_save_list_update_and_delete(as_raul, seed):
    saved = save(as_raul)
    assert saved["mine"] is True and saved["definition"]["measure"] == "spent"
    assert [r["name"] for r in as_raul.get("/api/v1/reports").json()] == ["Gasto de octubre"]
    update = as_raul.put(
        f"/api/v1/reports/{saved['id']}",
        json={"name": "Ahorro", "shared": False, "definition": definition(measure="saved")},
    )
    assert update.status_code == 200 and update.json()["definition"]["measure"] == "saved"
    run_saved = as_raul.get(f"/api/v1/reports/{saved['id']}/run")
    assert Decimal(run_saved.json()["total"]["amount"]) == Decimal("300.00")
    assert as_raul.delete(f"/api/v1/reports/{saved['id']}").status_code == 204
    assert as_raul.get("/api/v1/reports").json() == []
    assert as_raul.get(f"/api/v1/reports/{saved['id']}/run").status_code == 404


def test_a_personal_report_does_not_exist_for_anyone_else(as_raul, as_elena, as_ana, seed):
    saved = save(as_raul)
    for other in (as_elena, as_ana):
        assert other.get("/api/v1/reports").json() == []
        assert other.get(f"/api/v1/reports/{saved['id']}/run").status_code == 404
        assert other.delete(f"/api/v1/reports/{saved['id']}").status_code == 404
        put = other.put(
            f"/api/v1/reports/{saved['id']}",
            json={"name": "x", "shared": True, "definition": definition()},
        )
        assert put.status_code == 404
    assert len(as_raul.get("/api/v1/reports").json()) == 1


def test_a_shared_report_shares_the_definition_not_the_data(as_raul, as_elena, as_ana, seed):
    saved = save(as_raul, shared=True)
    listed = as_elena.get("/api/v1/reports").json()
    assert [(r["name"], r["mine"]) for r in listed] == [("Gasto de octubre", False)]
    mine = as_raul.get(f"/api/v1/reports/{saved['id']}/run").json()
    hers = as_elena.get(f"/api/v1/reports/{saved['id']}/run").json()
    assert total(mine) == Decimal("112.74")
    assert total(hers) == Decimal("154.74")  # con sus permisos, no con los de Raúl
    # otro hogar: ni la lista ni el resultado
    assert as_ana.get("/api/v1/reports").json() == []
    assert as_ana.get(f"/api/v1/reports/{saved['id']}/run").status_code == 404


def test_only_the_owner_changes_a_shared_report(as_raul, as_elena, seed):
    saved = save(as_raul, shared=True)
    put = as_elena.put(
        f"/api/v1/reports/{saved['id']}",
        json={"name": "Mío ahora", "shared": True, "definition": definition()},
    )
    assert put.status_code == 422
    assert as_elena.delete(f"/api/v1/reports/{saved['id']}").status_code == 422
    assert as_raul.get("/api/v1/reports").json()[0]["name"] == "Gasto de octubre"


def test_a_shared_report_cannot_filter_by_a_personal_account(as_raul, seed):
    r = as_raul.post(
        "/api/v1/reports",
        json={
            "name": "Mi cuenta",
            "shared": True,
            "definition": definition(account_ids=[str(seed.raul_personal.id)]),
        },
    )
    assert r.status_code == 422
    # personal sí
    ok = as_raul.post(
        "/api/v1/reports",
        json={
            "name": "Mi cuenta",
            "shared": False,
            "definition": definition(account_ids=[str(seed.raul_personal.id)]),
        },
    )
    assert ok.status_code == 201


def test_saving_validates_the_account_filter_and_the_name(as_raul, seed):
    hidden = as_raul.post(
        "/api/v1/reports",
        json={
            "name": "x",
            "shared": False,
            "definition": definition(account_ids=[str(seed.elena_personal.id)]),
        },
    )
    assert hidden.status_code == 404
    blank = as_raul.post(
        "/api/v1/reports", json={"name": "   ", "shared": False, "definition": definition()}
    )
    assert blank.status_code == 422


def test_at_most_thirty_saved_reports_per_person(as_raul, as_elena, seed):
    for i in range(30):
        save(as_raul, name=f"Informe {i}")
    r = as_raul.post(
        "/api/v1/reports", json={"name": "Uno más", "shared": False, "definition": definition()}
    )
    assert r.status_code == 409
    save(as_elena, name="El de Elena")  # el límite es por persona


def test_a_shared_report_with_an_account_the_runner_cannot_see_runs_empty_not_wide(
    as_raul, as_elena, seed, session_factory
):
    """Si la cuenta del filtro dejó de ser visible, no se ensancha a «todas»."""
    saved = save(as_raul, shared=True, account_ids=[str(seed.joint.id)])
    # la cuenta pasa a ser personal de Raúl: Elena ya no la ve
    from sqlalchemy import update

    from openfinance.infrastructure.db.models import AccountRow

    with session_factory() as s:
        s.execute(
            update(AccountRow)
            .where(AccountRow.id == seed.joint.id)
            .values(kind="personal", owner_id=seed.raul.id)
        )
        s.commit()
    hers = as_elena.get(f"/api/v1/reports/{saved['id']}/run").json()
    assert hers["rows"] == [] and Decimal(hers["total"]["amount"]) == 0
    assert hers["ignored_accounts"] == 1


def test_requires_a_session(app, seed):
    anonymous = TestClient(app, headers=CSRF)
    assert anonymous.get("/api/v1/reports").status_code == 401
    assert anonymous.post("/api/v1/reports/run", json=definition()).status_code == 401
