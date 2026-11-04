"""Clasificar varios a la vez y movimientos manuales (OF-705, ADR-0017)."""

from datetime import date

import pytest

from openfinance.api.v1 import insights as insights_api

from .test_changes_api import category, tx, tx_id
from .test_imports_api import commit, upload


@pytest.fixture(autouse=True)
def november(monkeypatch):
    monkeypatch.setattr(insights_api, "local_today", lambda: date(2026, 11, 15))


def eur(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "EUR"}


def spent(client, month: str = "2026-10") -> dict:
    return client.get("/api/v1/insights/month", params={"month": month}).json()["spent"]


class TestBulk:
    def test_one_operation_for_many_and_no_rule_is_learned(self, as_raul) -> None:
        ids = [tx_id(as_raul, "Glovo"), tx_id(as_raul, "Mercadona")]
        ocio = category(as_raul, "ocio")
        r = as_raul.post("/api/v1/transactions/categorize", json={"ids": ids, "category_id": ocio})
        assert r.status_code == 200
        assert r.json()["updated"] == 2
        assert {tx(as_raul, d)["category_id"] for d in ("Glovo", "Mercadona")} == {ocio}
        ops = as_raul.get("/api/v1/changes").json()
        assert [o["summary"] for o in ops] == ["2 gastos → Ocio"]
        assert {c["entity"] for c in ops[0]["changes"]} == {"transaction"}  # ninguna regla
        undo = as_raul.post(f"/api/v1/changes/{r.json()['operation_id']}/undo").json()
        assert undo["applied"] == 2
        assert tx(as_raul, "Glovo")["category_id"] is None
        assert tx(as_raul, "Mercadona")["category_id"] == category(as_raul, "super")

    def test_an_invisible_movement_rejects_the_whole_request(self, as_raul, as_elena) -> None:
        ids = [tx_id(as_raul, "Glovo"), tx_id(as_elena, "Peluquería")]
        r = as_raul.post("/api/v1/transactions/categorize", json={"ids": ids, "category_id": None})
        assert r.status_code == 404
        assert as_raul.get("/api/v1/changes").json() == []

    def test_only_expenses(self, as_raul) -> None:
        r = as_raul.post(
            "/api/v1/transactions/categorize",
            json={"ids": [tx_id(as_raul, "To pocket")], "category_id": category(as_raul, "ocio")},
        )
        assert r.status_code == 422


class TestManual:
    def cash(self, client, account_id, **extra):
        body = {
            "account_id": str(account_id),
            "booked_on": "2026-10-20",
            "description": "Churrería  del barrio",
            "amount": "7,50",
            **extra,
        }
        return client.post("/api/v1/transactions", json=body)

    def test_counts_in_the_totals_and_can_be_deleted_with_a_trace(self, as_raul, seed) -> None:
        before = spent(as_raul)
        r = self.cash(as_raul, seed.joint.id, category_id=category(as_raul, "restaurantes"))
        assert r.status_code == 201
        t = r.json()["transaction"]
        assert (t["amount"], t["source"], t["description"]) == (
            eur("-7.50"),
            "manual",
            "Churrería del barrio",
        )
        assert spent(as_raul)["amount"] == f"{float(before['amount']) + 7.5:.2f}"

        d = as_raul.delete(f"/api/v1/transactions/{t['id']}")
        assert d.status_code == 200
        assert as_raul.get("/api/v1/transactions", params={"q": "Churrer"}).json() == []
        assert spent(as_raul) == before
        history = as_raul.get(f"/api/v1/transactions/{t['id']}/history").json()
        assert [h["action"] for h in history] == ["transaction.create", "transaction.delete"]
        # Deshacer el borrado lo devuelve.
        as_raul.post(f"/api/v1/changes/{d.json()['operation_id']}/undo")
        assert len(as_raul.get("/api/v1/transactions", params={"q": "Churrer"}).json()) == 1

    def test_undoing_the_creation_voids_it(self, as_raul, seed) -> None:
        r = self.cash(as_raul, seed.joint.id).json()
        as_raul.post(f"/api/v1/changes/{r['operation_id']}/undo")
        assert as_raul.get("/api/v1/transactions", params={"q": "Churrer"}).json() == []

    def test_imported_movements_cannot_be_deleted(self, as_raul, seed) -> None:
        preview = upload(as_raul, seed.joint.id).json()
        assert commit(as_raul, preview["id"]).status_code == 200
        imported = as_raul.get("/api/v1/transactions", params={"q": "Iberdrola"}).json()[0]
        assert imported["source"].startswith("import:")
        r = as_raul.delete(f"/api/v1/transactions/{imported['id']}")
        assert r.status_code == 422
        assert "deshacer su importación" in r.json()["detail"]

    def test_income_is_positive(self, as_raul, seed) -> None:
        t = self.cash(as_raul, seed.joint.id, kind="income").json()["transaction"]
        assert t["amount"] == eur("7.50")

    @pytest.mark.parametrize(
        "extra",
        [{"amount": "0"}, {"amount": "-3"}, {"kind": "contribution"}, {"description": "   "}],
    )
    def test_invalid(self, as_raul, seed, extra) -> None:
        assert self.cash(as_raul, seed.joint.id, **extra).status_code == 422

    def test_partner_personal_account_and_other_household(
        self, as_raul, as_elena, as_ana, seed
    ) -> None:
        assert self.cash(as_raul, seed.elena_personal.id).status_code == 404
        assert self.cash(as_ana, seed.joint.id).status_code == 404
        mine = self.cash(as_elena, seed.elena_personal.id).json()["transaction"]["id"]
        assert as_raul.delete(f"/api/v1/transactions/{mine}").status_code == 404
        assert as_ana.delete(f"/api/v1/transactions/{mine}").status_code == 404

    def test_voided_movements_are_not_exported(self, as_raul, seed) -> None:
        t = self.cash(as_raul, seed.joint.id).json()["transaction"]
        as_raul.delete(f"/api/v1/transactions/{t['id']}")
        data = as_raul.get("/api/v1/export", params={"format": "json"}).json()
        assert t["id"] not in {x["id"] for x in data["transactions"]}
