"""OF-1504: exportación v2 y lo que nunca debe salir."""

import io
import json
import zipfile
from datetime import timedelta

import pytest

from openfinance.api.deps import get_bank_aggregator
from openfinance.api.export_formats import CSV_FILES_V1, CSV_FILES_V2, MANIFEST, V2_ONLY
from openfinance.infrastructure.time import local_today
from tests.db.test_bank_api import FakeAggregator, connect

TODAY = local_today()
OCT = {"from_month": "2026-10", "to_month": "2026-10", "measure": "spent", "group_by": "category"}


@pytest.fixture
def aggregator(app) -> FakeAggregator:
    fake = FakeAggregator()
    app.dependency_overrides[get_bank_aggregator] = lambda: fake
    return fake


def cat(client, slug="super") -> str:
    return next(c["id"] for c in client.get("/api/v1/categories").json() if c["slug"] == slug)


@pytest.fixture
def populated(as_raul, as_elena, seed, aggregator):
    sup = cat(as_raul)
    # presupuestos: un sobre con un importe propio de un mes
    assert (
        as_raul.put(
            f"/api/v1/budgets/{sup}", json={"amount": "300", "mode": "envelope"}
        ).status_code
        < 300
    )
    assert (
        as_raul.put(f"/api/v1/budgets/{sup}/months/2026-11", json={"amount": "350"}).status_code
        < 300
    )
    # objetivo con una aportación
    goal = as_raul.post("/api/v1/goals", json={"name": "Viaje", "target": "1000"}).json()
    as_raul.post(
        f"/api/v1/goals/{goal['id']}/contributions", json={"amount": "75.50", "note": "Paga"}
    )
    # pagos programados: uno de la conjunta, uno de la personal de Elena
    base = {
        "amount": "-900.00",
        "frequency": "monthly",
        "first_due": (TODAY + timedelta(days=5)).isoformat(),
    }
    as_raul.post(
        "/api/v1/schedule", json={**base, "name": "Alquiler", "account_id": str(seed.joint.id)}
    )
    as_elena.post(
        "/api/v1/schedule",
        json={**base, "name": "Gimnasio SECRETO", "account_id": str(seed.elena_personal.id)},
    )
    # plantillas
    tpl = {
        "kind": "expense",
        "amount": "1.80",
        "description": "Café",
        "account_id": str(seed.joint.id),
    }
    as_raul.post("/api/v1/templates", json={**tpl, "name": "Café del hogar"})
    as_elena.post(
        "/api/v1/templates",
        json={
            **tpl,
            "name": "Plantilla SECRETA",
            "account_id": str(seed.elena_personal.id),
            "personal": True,
        },
    )
    # reglas de automatización
    rule = {
        "conditions": [{"field": "description", "op": "contains", "value": "glovo"}],
        "actions": [{"type": "add_tags", "value": ["comida"]}],
    }
    as_raul.post("/api/v1/automation-rules", json={**rule, "name": "Regla del hogar"})
    as_elena.post(
        "/api/v1/automation-rules", json={**rule, "name": "Regla SECRETA", "personal": True}
    )
    # comercios con nombre propio: uno que Raúl ve y otro solo de la cuenta personal de Elena
    as_raul.post("/api/v1/merchants/rename", json={"key": "MERCADONA", "name": "El Mercadona"})
    as_elena.post(
        "/api/v1/merchants/rename", json={"key": "PELUQUERIA", "name": "Peluquería SECRETA"}
    )

    # informes guardados
    def report(client, name, shared):
        client.post("/api/v1/reports", json={"name": name, "shared": shared, "definition": OCT})

    report(as_raul, "Informe de Raúl", False)
    report(as_raul, "Informe compartido", True)
    report(as_elena, "Informe SECRETO de Elena", False)
    # conexiones bancarias (con sesión del agregador)
    mine = connect(as_raul, aggregator)
    as_raul.put(
        f"/api/v1/bank/connections/{mine['id']}/link",
        json={"remote_uid": "uid-1", "account_id": str(seed.raul_personal.id)},
    )
    connect(as_elena, aggregator, "Revolut")
    return seed


def export(client, version=None, fmt="json"):
    params = {"format": fmt, **({"version": version} if version else {})}
    return client.get("/api/v1/export", params=params)


def zip_files(content: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        return {n: z.read(n).decode("utf-8-sig") for n in z.namelist()}


def test_v2_is_the_default_and_carries_everything_new(as_raul, populated):
    body = export(as_raul).json()
    assert body["format_version"] == 2
    new_entities = {
        "budget_allocations",
        "goal_contributions",
        "scheduled_payments",
        "templates",
        "automation_rules",
        "merchants",
        "saved_reports",
        "bank_connections",
        "bank_links",
    }
    assert new_entities <= set(body)
    assert body["budgets"][0]["mode"] == "envelope" and body["budgets"][0]["started"]
    assert [(a["month"], a["amount"]) for a in body["budget_allocations"]] == [
        ("2026-11", "350.00")
    ]
    assert [(c["amount"], c["note"]) for c in body["goal_contributions"]] == [("75.50", "Paga")]
    assert [p["name"] for p in body["scheduled_payments"]] == ["Alquiler"]
    assert [t["name"] for t in body["templates"]] == ["Café del hogar"]
    assert [(r["name"], r["scope"]) for r in body["automation_rules"]] == [
        ("Regla del hogar", "household")
    ]
    assert [m["name"] for m in body["merchants"]] == ["El Mercadona"]
    assert {r["name"] for r in body["saved_reports"]} == {"Informe de Raúl", "Informe compartido"}
    assert [c["bank"] for c in body["bank_connections"]] == ["Bankinter"]
    first = body["bank_links"][0]
    assert (first["name"], first["iban_tail"]) == ("Cuenta corriente", "1234")


def test_a_saved_report_exports_its_definition_never_results(as_raul, populated):
    body = export(as_raul).json()
    definition = json.loads(body["saved_reports"][0]["definition"])
    assert set(definition) == {
        "from_month", "to_month", "measure", "group_by", "account_ids", "category_ids",
        "uncategorized", "tags", "min_amount",
    }  # fmt: skip


@pytest.mark.parametrize("fmt", ["json", "csv"])
def test_nothing_of_the_partner_or_another_household_leaves(as_raul, populated, fmt):
    response = export(as_raul, fmt=fmt)
    blob = response.text if fmt == "json" else "\n".join(zip_files(response.content).values())
    for secret in ("SECRET", str(populated.elena_personal.id), "Revolut"):
        assert secret not in blob, secret
    assert str(populated.other_joint.id) not in blob


def test_elena_gets_hers_and_not_raul(as_elena, populated):
    body = export(as_elena).json()
    assert [p["name"] for p in body["scheduled_payments"]] == ["Alquiler", "Gimnasio SECRETO"]
    assert {t["name"] for t in body["templates"]} == {"Café del hogar", "Plantilla SECRETA"}
    assert {r["name"] for r in body["saved_reports"]} == {
        "Informe compartido",
        "Informe SECRETO de Elena",
    }
    assert [c["bank"] for c in body["bank_connections"]] == ["Revolut"]
    assert {r["name"] for r in body["automation_rules"]} == {"Regla del hogar", "Regla SECRETA"}
    assert "Peluquería SECRETA" in {m["name"] for m in body["merchants"]}
    assert "Informe de Raúl" not in json.dumps(body, ensure_ascii=False)


@pytest.mark.parametrize("fmt", ["json", "csv"])
def test_credentials_and_internal_state_never_leave(as_raul, populated, aggregator, fmt):
    response = export(as_raul, fmt=fmt)
    blob = response.text if fmt == "json" else "\n".join(zip_files(response.content).values())
    state = aggregator.started[0][2]
    for forbidden in ("sess-secret-1", state, "session_id", "state", "vapid", "endpoint",
                      "fingerprint", "password_hash", "bank_ref"):  # fmt: skip
        assert forbidden not in blob, forbidden


def test_the_csv_zip_has_one_file_per_v2_entity(as_raul, populated):
    files = zip_files(export(as_raul, fmt="csv").content)
    assert set(files) == {MANIFEST, *(f"{n}.csv" for n in CSV_FILES_V2)}
    assert json.loads(files[MANIFEST])["format_version"] == 2
    assert (
        files["budgets.csv"].splitlines()[0] == '"category_id","amount","currency","mode","started"'
    )
    header = files["bank_links.csv"].splitlines()[0].replace('"', "").split(",")
    assert "iban" not in header and "iban_tail" in header


def test_v1_is_unchanged_with_version_1(as_raul, populated):
    body = export(as_raul, version=1).json()
    assert body["format_version"] == 1
    assert not (V2_ONLY & set(body))
    assert set(body["budgets"][0]) == {"category_id", "amount", "currency"}
    files = zip_files(export(as_raul, version=1, fmt="csv").content)
    assert set(files) == {MANIFEST, *(f"{n}.csv" for n in CSV_FILES_V1)}
    assert json.loads(files[MANIFEST])["format_version"] == 1
    assert "SECRET" not in json.dumps(body)


def test_unknown_versions_are_refused(as_raul, seed):
    for bad in (0, 3, "x"):
        assert as_raul.get("/api/v1/export", params={"version": bad}).status_code == 422


def test_a_link_to_an_account_you_cannot_see_is_dropped(
    as_raul, as_elena, populated, aggregator, seed
):
    """Elena enlaza su cuenta personal: en su exportación sale; la de Raúl no la nombra."""
    body = export(as_elena).json()
    elena_conn = body["bank_connections"][0]
    as_elena.put(
        f"/api/v1/bank/connections/{elena_conn['id']}/link",
        json={"remote_uid": "uid-1", "account_id": str(seed.elena_personal.id)},
    )
    assert export(as_elena).json()["bank_links"][0]["account_id"] == str(seed.elena_personal.id)
    assert str(seed.elena_personal.id) not in export(as_raul).text
