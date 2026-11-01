# ruff: noqa: DTZ001  (la hora local del banco no lleva zona)
"""OF-1001: comercios con nombre propio, renombrar y fusionar, con privacidad y deshacer."""

from datetime import datetime
from uuid import uuid4

import pytest

from openfinance.domain.categories import HOUSEHOLD_SCOPE, CategoryRule
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from tests.db.conftest import CSRF


def merchants(client) -> dict[str, dict]:
    """Los comercios que ve ese cliente, por nombre."""
    rows = client.get("/api/v1/merchants").json()
    return {m["name"]: m for m in rows}


def add_tx(session_factory, account, description: str, amount: str, when: datetime) -> None:
    with session_factory() as s:
        SqlUnitOfWork(s).transactions.add(
            Transaction(
                id=TransactionId(uuid4()),
                household_id=account.household_id,
                account_id=account.id,
                booked_at=when,
                value_date=when.date(),
                description=description,
                amount=Money.of(amount, "EUR"),
                kind=TransactionKind.EXPENSE,
            )
        )
        s.commit()


def names_in_listing(client) -> set[str]:
    return {t["merchant"] for t in client.get("/api/v1/transactions").json()}


class TestList:
    def test_groups_by_variant_and_counts_only_what_you_see(self, as_raul, seed) -> None:
        got = merchants(as_raul)
        assert got["Mercadona"]["count"] == 2
        assert got["Mercadona"]["keys"] == ["MERCADONA"]
        assert got["Mercadona"]["total"]["amount"] == "-147.34"
        assert got["Mercadona"]["id"] is None  # nadie le ha puesto nombre propio

    def test_does_not_list_a_merchant_only_the_partner_can_see(
        self, as_raul, as_elena, seed
    ) -> None:
        assert "Peluqueria" not in merchants(as_raul)
        assert "Peluqueria" in merchants(as_elena)
        assert "Mercadona Vecinos" not in merchants(as_raul)  # otro hogar


class TestRename:
    def test_renames_and_shows_the_name_on_the_movements(self, as_raul, seed) -> None:
        r = as_raul.post(
            "/api/v1/merchants/rename", json={"key": "MERCADONA", "name": "El Mercadona"}
        )
        assert r.status_code == 200
        assert r.json()["merchant"]["name"] == "El Mercadona"
        assert r.json()["merchant"]["id"] is not None
        assert "El Mercadona" in names_in_listing(as_raul)

    def test_undo_and_redo(self, as_raul, seed) -> None:
        op = as_raul.post(
            "/api/v1/merchants/rename", json={"key": "MERCADONA", "name": "El Mercadona"}
        ).json()["operation_id"]
        assert as_raul.post(f"/api/v1/changes/{op}/undo").json()["applied"] >= 1
        assert "Mercadona" in names_in_listing(as_raul)
        assert "El Mercadona" not in names_in_listing(as_raul)
        assert as_raul.post(f"/api/v1/changes/{op}/redo").status_code == 200
        assert "El Mercadona" in names_in_listing(as_raul)

    def test_renaming_twice_keeps_one_merchant(self, as_raul, seed) -> None:
        as_raul.post("/api/v1/merchants/rename", json={"key": "MERCADONA", "name": "Uno"})
        r = as_raul.post("/api/v1/merchants/rename", json={"key": "MERCADONA", "name": "Dos"})
        assert r.status_code == 200
        assert [m for m in merchants(as_raul) if m in ("Uno", "Dos")] == ["Dos"]

    def test_a_name_already_in_use_is_a_conflict(self, as_raul, seed) -> None:
        r = as_raul.post("/api/v1/merchants/rename", json={"key": "MERCADONA", "name": "glovo dto"})
        assert r.status_code == 409

    @pytest.mark.parametrize("name", ["   ", "x" * 61])
    def test_rejects_an_empty_or_long_name(self, as_raul, seed, name) -> None:
        r = as_raul.post("/api/v1/merchants/rename", json={"key": "MERCADONA", "name": name})
        assert r.status_code == 422

    def test_unknown_merchant_is_404(self, as_raul, seed) -> None:
        r = as_raul.post("/api/v1/merchants/rename", json={"key": "NO EXISTE", "name": "X"})
        assert r.status_code == 404

    def test_requires_the_csrf_header_and_a_session(self, client, seed) -> None:
        assert client.get("/api/v1/merchants").status_code == 401
        assert (
            client.post(
                "/api/v1/merchants/rename", json={"key": "A", "name": "B"}, headers=CSRF
            ).status_code
            == 401
        )


class TestMerge:
    @pytest.fixture
    def valencia(self, session_factory, seed):
        add_tx(
            session_factory, seed.joint, "Mercadona Valencia", "-12.00", datetime(2026, 10, 12, 10)
        )
        add_tx(
            session_factory, seed.joint, "Mercadona Valencia", "-8.00", datetime(2026, 10, 13, 10)
        )
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            super_ = next(
                c.id
                for c in uow.categories.for_household(seed.joint.household_id)
                if c.slug == "super"
            )
            uow.rules.upsert(
                CategoryRule(seed.joint.household_id, "MERCADONA", super_, HOUSEHOLD_SCOPE),
                datetime(2026, 10, 1),
            )
            s.commit()
        return super_

    def test_merges_the_variants_under_the_target_name(self, as_raul, seed, valencia) -> None:
        r = as_raul.post(
            "/api/v1/merchants/merge",
            json={"target_key": "MERCADONA", "source_key": "MERCADONA VALENCIA"},
        )
        assert r.status_code == 200
        merged = r.json()["merchant"]
        assert merged["keys"] == ["MERCADONA", "MERCADONA VALENCIA"]
        assert merged["count"] == 4
        assert "Mercadona Valencia" not in merchants(as_raul)
        # Todas las variantes se enseñan con el nombre del comercio.
        assert names_in_listing(as_raul) >= {"Mercadona"}
        assert not any("Valencia" in n for n in names_in_listing(as_raul))

    def test_reclassifies_the_uncategorized_ones_with_the_targets_category(
        self, as_raul, seed, valencia
    ) -> None:
        r = as_raul.post(
            "/api/v1/merchants/merge",
            json={"target_key": "MERCADONA", "source_key": "MERCADONA VALENCIA"},
        ).json()
        assert r["reclassified"] == 2
        rows = [
            t for t in as_raul.get("/api/v1/transactions").json() if "Valencia" in t["description"]
        ]
        assert {t["category_id"] for t in rows} == {str(valencia)}
        # y las próximas importaciones de la variante se clasifican solas
        assert any(
            rule["category_id"] == str(valencia)
            for rule in as_raul.get("/api/v1/rules").json()
            if "VALENCIA" in rule["merchant"].upper()
        )

    def test_undo_separates_them_again_and_restores_the_categories(
        self, as_raul, seed, valencia
    ) -> None:
        op = as_raul.post(
            "/api/v1/merchants/merge",
            json={"target_key": "MERCADONA", "source_key": "MERCADONA VALENCIA"},
        ).json()["operation_id"]
        undone = as_raul.post(f"/api/v1/changes/{op}/undo")
        assert undone.status_code == 200 and undone.json()["kept"] == 0
        after = merchants(as_raul)
        assert after["Mercadona"]["keys"] == ["MERCADONA"]
        assert after["Mercadona Valencia"]["keys"] == ["MERCADONA VALENCIA"]
        rows = [
            t for t in as_raul.get("/api/v1/transactions").json() if "Valencia" in t["description"]
        ]
        assert {t["category_id"] for t in rows} == {None}
        assert as_raul.post(f"/api/v1/changes/{op}/redo").status_code == 200
        assert "Mercadona Valencia" not in merchants(as_raul)

    def test_merging_a_merchant_with_itself_is_rejected(self, as_raul, seed) -> None:
        r = as_raul.post(
            "/api/v1/merchants/merge", json={"target_key": "MERCADONA", "source_key": "MERCADONA"}
        )
        assert r.status_code == 422

    def test_a_merge_that_was_renamed_first_still_undoes_cleanly(
        self, as_raul, seed, valencia
    ) -> None:
        as_raul.post(
            "/api/v1/merchants/rename", json={"key": "MERCADONA", "name": "Super de siempre"}
        )
        op = as_raul.post(
            "/api/v1/merchants/merge",
            json={"target_key": "MERCADONA", "source_key": "MERCADONA VALENCIA"},
        ).json()["operation_id"]
        assert as_raul.post(f"/api/v1/changes/{op}/undo").status_code == 200
        after = merchants(as_raul)
        assert "Super de siempre" in after and "Mercadona Valencia" in after


class TestPrivacy:
    def test_cannot_rename_or_merge_what_only_the_partner_sees(
        self, as_raul, as_elena, seed
    ) -> None:
        r = as_raul.post("/api/v1/merchants/rename", json={"key": "PELUQUERIA", "name": "Mi pelu"})
        assert r.status_code == 404
        r = as_raul.post(
            "/api/v1/merchants/merge", json={"target_key": "MERCADONA", "source_key": "PELUQUERIA"}
        )
        assert r.status_code == 404
        r = as_raul.post(
            "/api/v1/merchants/merge", json={"target_key": "PELUQUERIA", "source_key": "MERCADONA"}
        )
        assert r.status_code == 404
        assert "Peluqueria" in merchants(as_elena)  # no se ha tocado

    def test_other_households_cannot_touch_ours(self, as_ana, seed) -> None:
        r = as_ana.post("/api/v1/merchants/rename", json={"key": "MERCADONA", "name": "Mío"})
        assert r.status_code == 404

    def test_a_shared_variant_never_counts_the_partners_personal_movements(
        self, as_raul, as_elena, session_factory, seed
    ) -> None:
        add_tx(
            session_factory, seed.elena_personal, "Mercadona", "-500.00", datetime(2026, 10, 20, 10)
        )
        assert merchants(as_raul)["Mercadona"]["count"] == 2
        assert merchants(as_raul)["Mercadona"]["total"]["amount"] == "-147.34"
        assert merchants(as_elena)["Mercadona"]["count"] == 3

    def test_partners_undo_of_a_merge_cannot_be_done_by_you(self, as_raul, as_elena, seed) -> None:
        op = as_elena.post(
            "/api/v1/merchants/rename", json={"key": "MERCADONA", "name": "De Elena"}
        ).json()["operation_id"]
        assert as_raul.post(f"/api/v1/changes/{op}/undo").status_code == 404
