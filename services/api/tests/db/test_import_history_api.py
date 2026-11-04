"""Historial de importaciones y deshacer una importación (OF-703, ADR-0017)."""

from .test_changes_api import patch, tx
from .test_imports_api import FIXTURE, commit, upload


def imported(client, seed) -> list[dict]:
    rows = client.get("/api/v1/transactions", params={"account_id": str(seed.joint.id)}).json()
    return [t for t in rows if t["source"].startswith("import:")]


def balance(client, seed) -> dict:
    return next(a for a in client.get("/api/v1/accounts").json() if a["id"] == str(seed.joint.id))[
        "balance"
    ]


def do_import(client, seed, content: bytes = FIXTURE) -> dict:
    preview = upload(client, seed.joint.id, content).json()
    return commit(client, preview["id"]).json()


class TestHistory:
    def test_lists_imports_of_visible_accounts_only(self, as_raul, as_elena, as_ana, seed) -> None:
        result = do_import(as_raul, seed)
        items = as_elena.get("/api/v1/imports").json()
        assert [(i["id"], i["filename"], i["created"], i["can_undo"]) for i in items] == [
            (result["id"], "revolut.csv", result["created"], True)
        ]
        assert items[0]["created_by"] == str(seed.raul.id)
        assert as_ana.get("/api/v1/imports").json() == []


class TestUndo:
    def test_undo_then_reimport_gives_the_same_result(self, as_raul, seed) -> None:
        before_balance = balance(as_raul, seed)
        first = do_import(as_raul, seed)
        rows = imported(as_raul, seed)
        assert len(rows) == first["created"] > 0
        r = as_raul.post(f"/api/v1/imports/{first['id']}/undo")
        assert r.status_code == 200
        assert r.json()["voided"] == first["created"]
        assert imported(as_raul, seed) == []
        assert balance(as_raul, seed) == before_balance
        assert as_raul.get("/api/v1/imports").json()[0]["status"] == "undone"

        again = do_import(as_raul, seed)
        assert (again["created"], again["duplicates"]) == (first["created"], first["duplicates"])
        # Vuelven los mismos movimientos (mismo id), no copias nuevas.
        assert sorted(t["id"] for t in imported(as_raul, seed)) == sorted(t["id"] for t in rows)

    def test_corrections_survive_undo_and_redo(self, as_raul, seed) -> None:
        first = do_import(as_raul, seed)
        target = tx(as_raul, "Iberdrola")
        patch(as_raul, target["id"], note="Luz de octubre")
        op = as_raul.post(f"/api/v1/imports/{first['id']}/undo").json()["operation_id"]
        assert as_raul.post(f"/api/v1/changes/{op}/undo").json()["kept"] == 0
        assert tx(as_raul, "Iberdrola")["note"] == "Luz de octubre"
        assert as_raul.get("/api/v1/imports").json()[0]["status"] == "committed"

    def test_only_the_latest_import_of_the_account(self, as_raul, seed) -> None:
        first = do_import(as_raul, seed)
        when = b"2026-10-12 09:00:00,2026-10-12 09:00:01"
        extra = b"CARD_PAYMENT,Current," + when + b",Kiosko,-1.00,0.00,EUR,COMPLETED,2618.69\n"
        second = do_import(as_raul, seed, FIXTURE + extra)
        assert second["created"] == 1
        items = {i["id"]: i for i in as_raul.get("/api/v1/imports").json()}
        assert (items[first["id"]]["can_undo"], items[second["id"]]["can_undo"]) == (False, True)
        assert as_raul.post(f"/api/v1/imports/{first['id']}/undo").status_code == 422
        assert as_raul.post(f"/api/v1/imports/{second['id']}/undo").status_code == 200
        assert as_raul.post(f"/api/v1/imports/{second['id']}/undo").status_code == 409
        assert as_raul.post(f"/api/v1/imports/{first['id']}/undo").status_code == 200

    def test_cannot_undo_an_import_of_the_partner_personal_account(
        self, as_raul, as_elena, as_ana, seed
    ) -> None:
        from .test_xlsx_imports_api import bankinter_xlsx  # extracto sintético de Bankinter

        preview = as_elena.post(
            "/api/v1/imports",
            data={"account_id": str(seed.elena_personal.id)},
            files={"file": ("bankinter.xlsx", bankinter_xlsx(), "application/octet-stream")},
        ).json()
        result = commit(as_elena, preview["id"]).json()
        assert as_raul.post(f"/api/v1/imports/{result['id']}/undo").status_code == 404
        assert as_ana.post(f"/api/v1/imports/{result['id']}/undo").status_code == 404
        assert [i["id"] for i in as_raul.get("/api/v1/imports").json()] == []
        assert as_elena.post(f"/api/v1/imports/{result['id']}/undo").status_code == 200
