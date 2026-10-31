"""OF-201, OF-202 y OF-203: categorías, reglas por comercio y corrección de categoría."""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork

FIXTURE = (Path(__file__).parents[1] / "fixtures" / "revolut_joint_synthetic.csv").read_bytes()


@pytest.fixture
def add_tx(session_factory):
    def add(account, description, amount="-10.00", category=None, kind=TransactionKind.EXPENSE):
        tid = TransactionId(uuid4())
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            uow.transactions.add(
                Transaction(
                    id=tid,
                    household_id=account.household_id,
                    account_id=account.id,
                    booked_at=datetime(2026, 10, 15, 12, 0),  # noqa: DTZ001
                    value_date=datetime(2026, 10, 15).date(),  # noqa: DTZ001
                    description=description,
                    amount=Money.of(amount, "EUR"),
                    kind=kind,
                    category_id=category,
                )
            )
            uow.commit()
        return str(tid)

    return add


def cats(client):
    return {c["slug"] or c["name"]: c for c in client.get("/api/v1/categories").json()}


def categorize(client, tx_id, category_id, learn=True):
    return client.patch(
        f"/api/v1/transactions/{tx_id}", json={"category_id": category_id, "learn": learn}
    )


def category_of(client, description):
    rows = client.get("/api/v1/transactions", params={"q": description}).json()
    return {r["description"]: r["category_id"] for r in rows}


class TestCategories:
    def test_household_starts_with_13_default_categories(self, as_raul) -> None:
        body = as_raul.get("/api/v1/categories").json()
        assert len(body) == 13
        assert body[0] == {
            "id": body[0]["id"],
            "name": "Vivienda",
            "icon": "🏠",
            "color": "#0f766e",
            "hidden": False,
            "slug": "vivienda",
        }

    def test_create_and_reject_duplicates_ignoring_case_and_accents(self, as_raul) -> None:
        r = as_raul.post("/api/v1/categories", json={"name": "Mascotas", "icon": "🐶"})
        assert r.status_code == 201
        assert r.json()["slug"] is None
        dup = as_raul.post("/api/v1/categories", json={"name": "  SUPERMERCÁDO "})
        assert dup.status_code == 409
        assert (
            as_raul.post("/api/v1/categories", json={"name": "X", "color": "rojo"}).status_code
            == 422
        )

    def test_rename_recolor_and_hide(self, as_raul) -> None:
        ocio = cats(as_raul)["ocio"]
        r = as_raul.patch(
            f"/api/v1/categories/{ocio['id']}",
            json={"name": "Ocio y cultura", "color": "#123456", "hidden": True},
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Ocio y cultura"
        assert r.json()["hidden"] is True
        clash = as_raul.patch(f"/api/v1/categories/{ocio['id']}", json={"name": "Ropa"})
        assert clash.status_code == 409

    def test_hiding_a_category_keeps_its_transactions(self, as_raul) -> None:
        super_ = cats(as_raul)["super"]["id"]
        as_raul.patch(f"/api/v1/categories/{super_}", json={"hidden": True})
        assert set(category_of(as_raul, "Mercadona").values()) == {super_}

    def test_other_household_cannot_edit_my_categories(self, as_raul, as_ana) -> None:
        mine = cats(as_raul)["super"]["id"]
        assert as_ana.patch(f"/api/v1/categories/{mine}", json={"name": "Hack"}).status_code == 404
        assert cats(as_raul)["super"]["name"] == "Supermercado"


class TestCategorize:
    def test_correcting_one_merchant_teaches_a_rule(self, as_raul, seed, add_tx) -> None:
        target = add_tx(seed.joint, "MERCADONA 1234")
        variant = add_tx(seed.joint, "MERCADONA 0087")
        longer = add_tx(seed.joint, "COMPRA TARJETA 4821 MERCADONA VALENCIA")
        manual = add_tx(seed.joint, "MERCADONA 55", category=None)
        hogar = cats(as_raul)["hogar"]["id"]
        categorize(as_raul, manual, hogar, learn=False)
        other = add_tx(seed.joint, "MERCADERIAS LOPEZ")
        super_ = cats(as_raul)["super"]["id"]

        r = categorize(as_raul, target, super_)
        assert r.status_code == 200
        body = r.json()
        assert body["transaction"]["category_id"] == super_
        assert body["rule"] == {"merchant": "Mercadona", "category_id": super_}
        assert body["also_categorized"] == 2

        rows = {r["id"]: r["category_id"] for r in as_raul.get("/api/v1/transactions").json()}
        assert rows[variant] == super_
        assert rows[longer] == super_
        assert rows[manual] == hogar  # nunca pisa una categoría elegida
        assert rows[other] is None

    def test_rule_does_not_touch_partner_personal_account(
        self, as_raul, as_elena, seed, add_tx
    ) -> None:
        target = add_tx(seed.joint, "MERCADONA 1234")
        private = add_tx(seed.elena_personal, "MERCADONA 77")
        categorize(as_raul, target, cats(as_raul)["super"]["id"])
        mine = {r["id"]: r["category_id"] for r in as_elena.get("/api/v1/transactions").json()}
        assert mine[private] is None

    def test_without_learning_only_that_transaction_changes(self, as_raul, seed, add_tx) -> None:
        target = add_tx(seed.joint, "LIDL 1")
        sibling = add_tx(seed.joint, "LIDL 2")
        body = categorize(as_raul, target, cats(as_raul)["super"]["id"], learn=False).json()
        assert body["rule"] is None
        assert body["also_categorized"] == 0
        rows = {r["id"]: r["category_id"] for r in as_raul.get("/api/v1/transactions").json()}
        assert rows[sibling] is None

    def test_clear_category(self, as_raul, seed, add_tx) -> None:
        tid = add_tx(seed.joint, "ZARA", category=None)
        categorize(as_raul, tid, cats(as_raul)["ropa"]["id"])
        r = categorize(as_raul, tid, None)
        assert r.json()["transaction"]["category_id"] is None

    def test_only_expenses_can_be_categorized(self, as_raul, seed, add_tx) -> None:
        tid = add_tx(seed.joint, "To pocket", "-50.00", kind=TransactionKind.SAVINGS_TRANSFER)
        r = categorize(as_raul, tid, cats(as_raul)["otros"]["id"])
        assert r.status_code == 422

    def test_hidden_category_cannot_be_assigned(self, as_raul, seed, add_tx) -> None:
        ropa = cats(as_raul)["ropa"]["id"]
        as_raul.patch(f"/api/v1/categories/{ropa}", json={"hidden": True})
        assert categorize(as_raul, add_tx(seed.joint, "ZARA"), ropa).status_code == 422

    def test_isolation(self, as_raul, as_ana, seed, add_tx) -> None:
        partner = add_tx(seed.elena_personal, "PELUQUERIA")
        foreign = add_tx(seed.other_joint, "MERCADONA VECINOS")
        mine = add_tx(seed.joint, "ALDI")
        super_ = cats(as_raul)["super"]["id"]
        assert categorize(as_raul, partner, super_).status_code == 404
        assert categorize(as_raul, foreign, super_).status_code == 404
        their_category = cats(as_ana)["super"]["id"]
        assert categorize(as_raul, mine, their_category).status_code == 404

    def test_uncategorized_count_respects_privacy(self, as_raul, as_elena) -> None:
        # Glovo en la conjunta; la peluquería es de la cuenta personal de Elena.
        assert as_raul.get("/api/v1/transactions/uncategorized-count").json() == {"count": 1}
        assert as_elena.get("/api/v1/transactions/uncategorized-count").json() == {"count": 2}

    def test_merchant_is_exposed_readably(self, as_raul) -> None:
        rows = as_raul.get("/api/v1/transactions", params={"q": "Glovo"}).json()
        assert rows[0]["merchant"] == "Glovo Dto"


class TestRulesOnImport:
    def upload(self, client, account_id):
        return client.post(
            "/api/v1/imports",
            data={"account_id": str(account_id)},
            files={"file": ("revolut.csv", FIXTURE, "text/csv")},
        )

    def test_learned_rules_are_proposed_and_applied_on_import(self, as_raul, seed) -> None:
        c = cats(as_raul)
        mercadona = category_of(as_raul, "Mercadona")
        some_mercadona = next(iter(mercadona))
        row = as_raul.get("/api/v1/transactions", params={"q": some_mercadona}).json()[0]
        categorize(as_raul, row["id"], c["super"]["id"])

        p = self.upload(as_raul, seed.joint.id).json()
        proposed = {r["description"]: r["category_id"] for r in p["rows"]}
        assert proposed["Mercadona"] == c["super"]["id"]
        assert proposed["Iberdrola, S.A."] is None
        assert proposed["Payment from Raul Lopez"] is None  # las aportaciones no llevan categoría

        as_raul.post(f"/api/v1/imports/{p['id']}/commit")
        imported = category_of(as_raul, "Mercadona")
        assert set(imported.values()) == {c["super"]["id"]}

    def test_rules_pointing_to_hidden_categories_are_ignored(self, as_raul, seed) -> None:
        c = cats(as_raul)
        row = as_raul.get("/api/v1/transactions", params={"q": "Glovo"}).json()[0]
        categorize(as_raul, row["id"], c["restaurantes"]["id"])
        as_raul.patch(f"/api/v1/categories/{c['restaurantes']['id']}", json={"hidden": True})
        content = FIXTURE.replace(b"Mercadona", b"Glovo order")
        p = as_raul.post(
            "/api/v1/imports",
            data={"account_id": str(seed.joint.id)},
            files={"file": ("r.csv", content, "text/csv")},
        ).json()
        assert {r["description"]: r["category_id"] for r in p["rows"]}["Glovo order"] is None


class TestRuleScopeAndSafety:
    def upload(self, client, account_id, content):
        return client.post(
            "/api/v1/imports",
            data={"account_id": str(account_id)},
            files={"file": ("r.csv", content, "text/csv")},
        )

    def test_rule_learned_in_a_personal_account_stays_personal(
        self, as_raul, as_elena, seed, add_tx
    ) -> None:
        mine = add_tx(seed.raul_personal, "ZARA 123")
        mine_too = add_tx(seed.raul_personal, "ZARA 456")
        joint = add_tx(seed.joint, "ZARA 789")
        hers = add_tx(seed.elena_personal, "ZARA 000")
        ropa = cats(as_raul)["ropa"]["id"]

        r = categorize(as_raul, mine, ropa).json()
        assert r["also_categorized"] == 1
        rows = {t["id"]: t["category_id"] for t in as_raul.get("/api/v1/transactions").json()}
        assert rows[mine_too] == ropa
        assert rows[joint] is None  # no se propaga a la conjunta
        hers_rows = {t["id"]: t["category_id"] for t in as_elena.get("/api/v1/transactions").json()}
        assert hers_rows[hers] is None

        # Ni se propone al importar en la conjunta.
        header = FIXTURE.splitlines()[0]
        row = b"\nCARD_PAYMENT,Current,2026-11-01 10:00:00,2026-11-01 10:00:01,ZARA 1,-20.00,0,EUR,COMPLETED,1.00\n"  # noqa: E501
        p = self.upload(as_elena, seed.joint.id, header + row).json()
        assert p["rows"][0]["category_id"] is None

    def test_household_rule_also_helps_own_personal_account(self, as_raul, seed, add_tx) -> None:
        joint = add_tx(seed.joint, "DECATHLON 1")
        personal = add_tx(seed.raul_personal, "DECATHLON 2")
        salud = cats(as_raul)["salud"]["id"]
        assert categorize(as_raul, joint, salud).json()["also_categorized"] == 1
        rows = {t["id"]: t["category_id"] for t in as_raul.get("/api/v1/transactions").json()}
        assert rows[personal] == salud

    def test_clearing_the_category_forgets_the_rule(self, as_raul, seed, add_tx) -> None:
        tid = add_tx(seed.joint, "MERCADONA 1")
        super_ = cats(as_raul)["super"]["id"]
        categorize(as_raul, tid, super_)
        categorize(as_raul, tid, None)
        p = self.upload(as_raul, seed.joint.id, FIXTURE).json()
        assert {r["description"]: r["category_id"] for r in p["rows"]}["Mercadona"] is None

    def test_broad_merchants_do_not_learn(self, as_raul, seed, add_tx) -> None:
        tid = add_tx(seed.joint, "PAYPAL *X")
        other = add_tx(seed.joint, "PAYPAL *Y")
        body = categorize(as_raul, tid, cats(as_raul)["ocio"]["id"]).json()
        assert (body["rule"], body["also_categorized"]) == (None, 0)
        rows = {t["id"]: t["category_id"] for t in as_raul.get("/api/v1/transactions").json()}
        assert rows[other] is None

    def test_generic_card_prefix_does_not_collapse_merchants(self, as_raul, seed, add_tx) -> None:
        tid = add_tx(seed.joint, "PAGO CON TARJETA MERCADONA")
        other = add_tx(seed.joint, "PAGO CON TARJETA FARMACIA SOL")
        categorize(as_raul, tid, cats(as_raul)["super"]["id"])
        rows = {t["id"]: t["category_id"] for t in as_raul.get("/api/v1/transactions").json()}
        assert rows[other] is None
