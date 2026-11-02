"""OF-1103: importar OFX y QIF a una cuenta sin banco propio."""

from pathlib import Path

from tests.db.test_imports_api import commit

FIX = Path(__file__).parents[1] / "fixtures"


def account(client, name="Cuenta externa", currency=None):
    body = {"name": name, "type": "cash", "shared": True, "opening_balance": "0"}
    if currency:
        body["currency"] = currency
    return client.post("/api/v1/accounts", json=body).json()


def upload(client, account_id: str, name: str, mime: str = "application/octet-stream"):
    return client.post(
        "/api/v1/imports",
        data={"account_id": account_id},
        files={"file": (name, (FIX / name).read_bytes(), mime)},
    )


class TestOfx:
    def test_preview_commit_and_idempotence(self, as_raul, seed) -> None:
        a = account(as_raul)
        preview = upload(as_raul, a["id"], "synthetic.ofx")
        assert preview.status_code == 201
        p = preview.json()
        assert (p["new_count"], p["duplicate_count"], p["skipped_count"]) == (4, 0, 2)
        assert p["bank_balance"] == {"amount": "1461.92", "currency": "EUR"}
        assert commit(as_raul, p["id"]).status_code == 200
        again = upload(as_raul, a["id"], "synthetic.ofx").json()
        assert (again["new_count"], again["duplicate_count"]) == (0, 4)

    def test_the_balance_after_import_adds_the_new_rows(self, as_raul, seed) -> None:
        a = account(as_raul)
        p = upload(as_raul, a["id"], "synthetic.ofx").json()
        # 1600 - 87.34 - 25.40 - 25.40
        assert p["balance_after_import"]["amount"] == "1461.86"

    def test_a_different_currency_is_skipped_with_a_reason(self, as_raul, seed) -> None:
        a = account(as_raul, "En dólares", currency="USD")
        p = upload(as_raul, a["id"], "synthetic.ofx").json()
        assert p["new_count"] == 0
        assert any("moneda EUR distinta" in s["reason"] for s in p["skipped"])

    def test_rows_get_the_same_treatment_as_any_import(self, as_raul, seed) -> None:
        a = account(as_raul)
        commit(as_raul, upload(as_raul, a["id"], "synthetic.ofx").json()["id"])
        rows = as_raul.get("/api/v1/transactions", params={"account_id": a["id"]}).json()
        assert {r["kind"] for r in rows} == {"income", "expense"}
        assert all(r["source"] == "import:synthetic.ofx" for r in rows)

    def test_undoing_it_removes_only_those_rows(self, as_raul, seed) -> None:
        a = account(as_raul)
        done = commit(as_raul, upload(as_raul, a["id"], "synthetic.ofx").json()["id"]).json()
        assert as_raul.post(f"/api/v1/imports/{done['id']}/undo").json()["voided"] == 4
        assert as_raul.get("/api/v1/transactions", params={"account_id": a["id"]}).json() == []


class TestQif:
    def test_imports_with_the_accounts_currency(self, as_raul, seed) -> None:
        a = account(as_raul, "Libreta", currency="USD")
        p = upload(as_raul, a["id"], "synthetic.qif").json()
        assert p["new_count"] == 4
        assert p["rows"][0]["amount"]["currency"] == "USD"

    def test_ambiguous_dates_are_a_clear_422(self, as_raul, seed) -> None:
        a = account(as_raul)
        r = upload(as_raul, a["id"], "synthetic_ambiguous.qif")
        assert r.status_code == 422 and "ambiguas" in r.json()["detail"]


class TestFormats:
    def test_unknown_files_get_a_helpful_422(self, as_raul, seed) -> None:
        a = account(as_raul)
        r = as_raul.post(
            "/api/v1/imports",
            data={"account_id": a["id"]},
            files={"file": ("raro.csv", b"a;b\n1;2\n", "text/csv")},
        )
        assert r.status_code == 422 and "Formato no reconocido" in r.json()["detail"]

    def test_the_partner_cannot_import_into_my_personal_account(
        self, as_raul, as_elena, seed
    ) -> None:
        mine = as_raul.post(
            "/api/v1/accounts",
            json={"name": "Mi efectivo", "type": "cash", "shared": False, "opening_balance": "0"},
        ).json()
        assert upload(as_elena, mine["id"], "synthetic.ofx").status_code == 404
