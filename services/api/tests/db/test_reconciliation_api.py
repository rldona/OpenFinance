"""OF-1006: movimientos revisados y comprobación del saldo contra el banco."""

# ruff: noqa: DTZ001  (la hora local del banco no lleva zona)
from datetime import datetime

from tests.db.test_imports_api import commit, upload
from tests.db.test_links_api import add


def txs(client, **params) -> list[dict]:
    return client.get("/api/v1/transactions", params=params).json()


def by_description(client, description: str) -> dict:
    return next(t for t in txs(client) if t["description"] == description)


def review(client, ids: list[str], reviewed: bool = True):
    return client.post("/api/v1/transactions/review", json={"ids": ids, "reviewed": reviewed})


class TestReview:
    def test_marks_and_filters(self, as_raul, seed) -> None:
        glovo = by_description(as_raul, "Glovo 50% dto")
        r = review(as_raul, [glovo["id"]])
        assert r.status_code == 200 and r.json()["changed"] == 1
        assert by_description(as_raul, "Glovo 50% dto")["reviewed"] is True
        done = txs(as_raul, reviewed="true")
        assert [t["description"] for t in done] == ["Glovo 50% dto"]
        assert "Glovo 50% dto" not in {t["description"] for t in txs(as_raul, reviewed="false")}

    def test_undo_redo_and_idempotence(self, as_raul, seed) -> None:
        glovo = by_description(as_raul, "Glovo 50% dto")["id"]
        op = review(as_raul, [glovo]).json()["operation_id"]
        again = review(as_raul, [glovo]).json()
        assert (again["changed"], again["operation_id"]) == (0, None)
        assert as_raul.post(f"/api/v1/changes/{op}/undo").json()["applied"] == 1
        assert by_description(as_raul, "Glovo 50% dto")["reviewed"] is False
        assert as_raul.post(f"/api/v1/changes/{op}/redo").status_code == 200
        assert by_description(as_raul, "Glovo 50% dto")["reviewed"] is True

    def test_ignores_what_you_cannot_see(self, as_raul, as_elena, seed) -> None:
        pelu = by_description(as_elena, "Peluquería")["id"]
        assert review(as_raul, [pelu]).json()["changed"] == 0
        assert by_description(as_elena, "Peluquería")["reviewed"] is False

    def test_a_reviewed_movement_survives_undoing_an_import(self, as_raul, seed) -> None:
        preview = upload(as_raul, seed.joint.id).json()
        done = commit(as_raul, preview["id"]).json()
        imported = [t for t in txs(as_raul) if t["source"].startswith("import:")]
        keep = imported[0]
        review(as_raul, [keep["id"]])
        r = as_raul.post(f"/api/v1/imports/{done['id']}/undo")
        assert r.status_code == 200
        assert r.json()["kept_reviewed"] == 1
        remaining = {t["id"] for t in txs(as_raul) if t["source"].startswith("import:")}
        assert remaining == {keep["id"]}

    def test_rules_do_not_reclassify_reviewed_ones(self, as_raul, seed, session_factory) -> None:
        first = add(
            session_factory, seed.joint, "Zara Valencia", "-30.00", datetime(2026, 10, 12, 9)
        )
        second = add(
            session_factory, seed.joint, "Zara Valencia", "-20.00", datetime(2026, 10, 13, 9)
        )
        third = add(
            session_factory, seed.joint, "Zara Valencia", "-10.00", datetime(2026, 10, 14, 9)
        )
        review(as_raul, [third])
        cat = next(c["id"] for c in as_raul.get("/api/v1/categories").json() if c["slug"] == "ropa")
        r = as_raul.patch(f"/api/v1/transactions/{first}", json={"category_id": cat})
        assert r.status_code == 200 and r.json()["also_categorized"] == 1
        cats = {t["id"]: t["category_id"] for t in txs(as_raul)}
        assert (cats[first], cats[second], cats[third]) == (cat, cat, None)

    def test_an_explicit_choice_on_a_reviewed_one_still_applies(self, as_raul, seed) -> None:
        glovo = by_description(as_raul, "Glovo 50% dto")["id"]
        review(as_raul, [glovo])
        cat = next(
            c["id"] for c in as_raul.get("/api/v1/categories").json() if c["slug"] == "restaurantes"
        )
        r = as_raul.post(
            "/api/v1/transactions/categorize", json={"ids": [glovo], "category_id": cat}
        )
        assert r.status_code == 200
        assert by_description(as_raul, "Glovo 50% dto")["category_id"] == cat


class TestReconcile:
    def reconcile(self, client, account, as_of: str, balance: str):
        return client.post(
            f"/api/v1/accounts/{account.id}/reconciliations",
            json={"as_of": as_of, "bank_balance": balance},
        )

    def test_matches_when_the_balance_is_the_same(self, as_raul, seed) -> None:
        # 100 + 1600 - 300 - 87.34 - 25.40 - 60 = 1227.26 a final de octubre
        r = self.reconcile(as_raul, seed.joint, "2026-10-31", "1227.26")
        assert r.status_code == 201
        body = r.json()
        assert body["matches"] is True and body["difference"]["amount"] == "0.00"
        assert body["computed_balance"]["amount"] == "1227.26"

    def test_reports_the_difference(self, as_raul, seed) -> None:
        body = self.reconcile(as_raul, seed.joint, "2026-10-31", "1300.00").json()
        assert body["matches"] is False
        assert body["difference"]["amount"] == "72.74"  # falta en OpenFinance

    def test_counts_only_up_to_the_date(self, as_raul, seed) -> None:
        # Hasta el 2 de octubre a mediodía: 100 + 1600 - 300 (septiembre: -60 antes)
        body = self.reconcile(as_raul, seed.joint, "2026-10-02", "1340.00").json()
        assert body["computed_balance"]["amount"] == "1340.00"
        assert body["matches"] is True

    def test_history_lists_the_latest_first(self, as_raul, seed) -> None:
        self.reconcile(as_raul, seed.joint, "2026-10-02", "1340.00")
        self.reconcile(as_raul, seed.joint, "2026-10-31", "1227.26")
        rows = as_raul.get(f"/api/v1/accounts/{seed.joint.id}/reconciliations").json()
        assert [r["as_of"] for r in rows] == ["2026-10-31", "2026-10-02"]

    def test_rejects_a_future_date_and_bad_amounts(self, as_raul, seed) -> None:
        assert self.reconcile(as_raul, seed.joint, "2999-01-01", "10").status_code == 422
        assert self.reconcile(as_raul, seed.joint, "2026-10-01", "mucho").status_code == 422

    def test_privacy(self, as_raul, as_elena, as_ana, seed) -> None:
        assert self.reconcile(as_raul, seed.elena_personal, "2026-10-31", "1").status_code == 404
        assert (
            as_raul.get(f"/api/v1/accounts/{seed.elena_personal.id}/reconciliations").status_code
            == 404
        )
        assert self.reconcile(as_ana, seed.joint, "2026-10-31", "1").status_code == 404
        self.reconcile(as_elena, seed.elena_personal, "2026-10-31", "658.00")
        assert as_raul.get(f"/api/v1/accounts/{seed.joint.id}/reconciliations").json() == []
