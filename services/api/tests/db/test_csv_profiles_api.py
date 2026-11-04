"""OF-1105: perfiles de CSV de cualquier banco."""

import json

import pytest

from tests.db.test_imports_api import commit

SPANISH = (
    "Extracto de cuenta;;;;\n"
    "Titular;SINTETICO;;;\n"
    "Fecha;Descripción;Detalle;Debe;Haber;Saldo\n"
    "03/10/2026;COMPRA;MERCADONA;87,34;;1.512,66\n"
    "01/10/2026;NOMINA;EMPRESA SINTETICA;;1.600,00;1.600,00\n"
    "07/10/2026;COMPRA;GLOVO;25,40;;1.487,26\n"
    "xx/10/2026;ROTA;FILA;1,00;;\n"
).encode("cp1252")

PROFILE = {
    "name": "Banco sintético",
    "delimiter": ";",
    "encoding": "cp1252",
    "skip_rows": 2,
    "has_header": True,
    "date_column": 0,
    "date_format": "%d/%m/%Y",
    "description_columns": [1, 2],
    "amount_mode": "debit_credit",
    "debit_column": 3,
    "credit_column": 4,
    "decimal_separator": ",",
    "invert_sign": False,
    "balance_column": 5,
}


def create(client, **kw):
    return client.post("/api/v1/csv-profiles", json={**PROFILE, **kw})


def account(client, name="Otro banco"):
    return client.post(
        "/api/v1/accounts",
        json={"name": name, "type": "cash", "shared": True, "opening_balance": "0"},
    ).json()


def upload(client, account_id, content=SPANISH, profile_id=None, name="banco.csv"):
    data = {"account_id": account_id}
    if profile_id:
        data["profile_id"] = profile_id
    return client.post("/api/v1/imports", data=data, files={"file": (name, content, "text/csv")})


class TestCrud:
    def test_create_list_update_delete_with_undo(self, as_raul, seed) -> None:
        r = create(as_raul)
        assert r.status_code == 201
        profile = r.json()["profile"]
        assert profile["name"] == "Banco sintético" and profile["debit_column"] == 3
        assert [p["name"] for p in as_raul.get("/api/v1/csv-profiles").json()] == [
            "Banco sintético"
        ]

        up = as_raul.put(f"/api/v1/csv-profiles/{profile['id']}", json={**PROFILE, "skip_rows": 3})
        assert up.json()["profile"]["skip_rows"] == 3
        assert (
            as_raul.post(f"/api/v1/changes/{up.json()['operation_id']}/undo").json()["applied"] == 1
        )
        assert as_raul.get("/api/v1/csv-profiles").json()[0]["skip_rows"] == 2

        gone = as_raul.delete(f"/api/v1/csv-profiles/{profile['id']}").json()["operation_id"]
        assert as_raul.get("/api/v1/csv-profiles").json() == []
        assert as_raul.post(f"/api/v1/changes/{gone}/undo").status_code == 200
        assert len(as_raul.get("/api/v1/csv-profiles").json()) == 1

    def test_the_name_must_be_unique(self, as_raul, seed) -> None:
        create(as_raul)
        assert create(as_raul, name="banco SINTÉTICO".replace("É", "é")).status_code in (201, 409)
        assert create(as_raul, name="banco sintético").status_code == 409

    @pytest.mark.parametrize(
        "change",
        [
            {"delimiter": "x"},
            {"date_format": "%d/%m/%Y %H:%M:%S%z"},
            {"debit_column": 3, "credit_column": 3},
            {"amount_mode": "single", "amount_column": None},
            {"description_columns": []},
            {"encoding": "ebcdic"},
            {"name": "   "},
        ],
    )
    def test_invalid_profiles_are_422(self, as_raul, seed, change) -> None:
        assert create(as_raul, **change).status_code == 422
        assert as_raul.get("/api/v1/csv-profiles").json() == []

    def test_profiles_are_per_household_and_need_a_session(
        self, as_raul, as_ana, client, seed
    ) -> None:
        p = create(as_raul).json()["profile"]
        assert as_ana.get("/api/v1/csv-profiles").json() == []
        assert as_ana.put(f"/api/v1/csv-profiles/{p['id']}", json=PROFILE).status_code == 404
        assert as_ana.delete(f"/api/v1/csv-profiles/{p['id']}").status_code == 404
        assert client.get("/api/v1/csv-profiles").status_code == 401

    def test_the_partner_sees_them_but_cannot_undo_the_other_ones_operation(
        self, as_raul, as_elena, seed
    ) -> None:
        op = create(as_raul).json()["operation_id"]
        assert len(as_elena.get("/api/v1/csv-profiles").json()) == 1
        assert as_elena.post(f"/api/v1/changes/{op}/undo").status_code == 404


class TestSampleAndTest:
    def test_sample_proposes_separator_and_encoding(self, as_raul, seed) -> None:
        r = as_raul.post(
            "/api/v1/csv-profiles/sample", files={"file": ("a.csv", SPANISH, "text/csv")}
        )
        body = r.json()
        assert (body["delimiter"], body["encoding"]) == (";", "cp1252")
        assert body["rows"][2][:2] == ["Fecha", "Descripción"]

    def test_test_reads_with_the_profile_and_saves_nothing(self, as_raul, seed) -> None:
        r = as_raul.post(
            "/api/v1/csv-profiles/test",
            data={"profile": json.dumps(PROFILE)},
            files={"file": ("a.csv", SPANISH, "text/csv")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3 and body["skipped_total"] == 1
        assert [x["amount"]["amount"] for x in body["rows"]] == ["1600.00", "-87.34", "-25.40"]
        assert body["skipped"][0]["reason"] == "fila no válida: fecha no válida"
        assert as_raul.get("/api/v1/csv-profiles").json() == []
        assert as_raul.get("/api/v1/transactions").json() != []  # solo lo de la semilla

    def test_a_wrong_profile_is_a_clear_422(self, as_raul, seed) -> None:
        bad = {**PROFILE, "encoding": "utf-8"}
        r = as_raul.post(
            "/api/v1/csv-profiles/test",
            data={"profile": json.dumps(bad)},
            files={"file": ("a.csv", SPANISH, "text/csv")},
        )
        assert r.status_code == 422 and "utf-8" in r.json()["detail"]
        broken = as_raul.post(
            "/api/v1/csv-profiles/test",
            data={"profile": "{no json"},
            files={"file": ("a.csv", SPANISH, "text/csv")},
        )
        assert broken.status_code == 422

    def test_empty_and_huge_files_are_refused(self, as_raul, seed) -> None:
        empty = as_raul.post(
            "/api/v1/csv-profiles/sample", files={"file": ("a.csv", b"", "text/csv")}
        )
        assert empty.status_code == 422
        huge = as_raul.post(
            "/api/v1/csv-profiles/sample",
            files={"file": ("a.csv", b"a;b\n" * (2 * 1024 * 1024), "text/csv")},
        )
        assert huge.status_code in (413, 422)


class TestImportWithAProfile:
    def test_preview_commit_and_idempotence(self, as_raul, seed) -> None:
        a = account(as_raul)
        p = create(as_raul).json()["profile"]
        preview = upload(as_raul, a["id"], profile_id=p["id"])
        assert preview.status_code == 201
        pv = preview.json()
        assert (pv["new_count"], pv["skipped_count"]) == (3, 1)
        assert pv["bank_balance"] == {"amount": "1487.26", "currency": "EUR"}
        assert pv["balance_mismatches"] == []
        assert commit(as_raul, pv["id"]).status_code == 200
        again = upload(as_raul, a["id"], profile_id=p["id"]).json()
        assert (again["new_count"], again["duplicate_count"]) == (0, 3)

    def test_a_csv_without_a_profile_asks_for_one(self, as_raul, seed) -> None:
        a = account(as_raul)
        r = upload(as_raul, a["id"])
        assert r.status_code == 422 and "crea antes un perfil" in r.json()["detail"]

    def test_an_unknown_or_foreign_profile_is_404(self, as_raul, as_ana, seed) -> None:
        a = account(as_raul)
        p = create(as_raul).json()["profile"]
        assert (
            upload(as_raul, a["id"], profile_id="00000000-0000-0000-0000-000000000000").status_code
            == 404
        )
        ana_account = account(as_ana, "De Ana")
        assert upload(as_ana, ana_account["id"], profile_id=p["id"]).status_code == 404

    def test_deleting_the_profile_before_confirming_is_a_conflict(self, as_raul, seed) -> None:
        a = account(as_raul)
        p = create(as_raul).json()["profile"]
        pv = upload(as_raul, a["id"], profile_id=p["id"]).json()
        as_raul.delete(f"/api/v1/csv-profiles/{p['id']}")
        assert commit(as_raul, pv["id"]).status_code == 409

    def test_the_partner_cannot_import_into_my_personal_account(
        self, as_raul, as_elena, seed
    ) -> None:
        mine = as_raul.post(
            "/api/v1/accounts",
            json={"name": "Mi efectivo", "type": "cash", "shared": False, "opening_balance": "0"},
        ).json()
        p = create(as_raul).json()["profile"]
        assert upload(as_elena, mine["id"], profile_id=p["id"]).status_code == 404

    def test_rules_apply_to_rows_read_with_a_profile(self, as_raul, seed) -> None:
        a = account(as_raul)
        p = create(as_raul).json()["profile"]
        as_raul.post(
            "/api/v1/automation-rules",
            json={
                "name": "Glovo",
                "conditions": [{"field": "description", "op": "contains", "value": "glovo"}],
                "actions": [{"type": "add_tags", "value": ["domicilio"]}],
            },
        )
        pv = upload(as_raul, a["id"], profile_id=p["id"]).json()
        assert [r["tags"] for r in pv["rows"] if "GLOVO" in r["description"]] == [["domicilio"]]
