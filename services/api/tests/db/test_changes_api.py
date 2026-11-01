"""Corregir movimientos y deshacer (OF-701, OF-706, ADR-0017).

Seed de conftest: conjunta con Mercadona (super), Glovo (sin categoría), aportación de Raúl y
traspaso a la hucha; Bankinter de Raúl y de Elena; Ana en otro hogar.
"""

import random
from datetime import date, datetime

import pytest

from openfinance.api.v1 import insights as insights_api
from openfinance.domain.ledger import TransactionKind
from openfinance.infrastructure.db.repositories import SqlUnitOfWork

from .conftest import _tx


@pytest.fixture(autouse=True)
def november(monkeypatch):
    monkeypatch.setattr(insights_api, "local_today", lambda: date(2026, 11, 15))


def tx_id(client, description: str) -> str:
    rows = client.get("/api/v1/transactions", params={"q": description}).json()
    assert rows, description
    return rows[0]["id"]


def tx(client, description: str) -> dict:
    return client.get("/api/v1/transactions", params={"q": description}).json()[0]


def patch(client, transaction_id: str, **body):
    return client.patch(f"/api/v1/transactions/{transaction_id}", json=body)


def category(client, slug: str) -> str:
    return next(c["id"] for c in client.get("/api/v1/categories").json() if c["slug"] == slug)


@pytest.fixture
def income(seed, session_factory) -> None:
    """Un Bizum recibido en la conjunta que en realidad es la aportación de Elena."""
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        when = datetime(2026, 10, 5, 12)  # noqa: DTZ001 - hora local del extracto
        uow.transactions.add(
            _tx(seed.joint, "200.00", "Bizum de E M", when, TransactionKind.INCOME)
        )
        uow.commit()


class TestEdit:
    def test_income_to_contribution_changes_inflow_and_saving(self, as_raul, seed, income) -> None:
        def month():
            return as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()

        before = month()
        r = patch(
            as_raul,
            tx_id(as_raul, "Bizum de E M"),
            kind="contribution",
            member_id=str(seed.elena.id),
        )
        assert r.status_code == 200
        assert r.json()["transaction"]["kind"] == "contribution"
        after = month()
        assert before["income"] == {"amount": "200.00", "currency": "EUR"}
        assert after["income"] == {"amount": "0.00", "currency": "EUR"}
        assert after["inflow"] == before["inflow"]  # sigue entrando, ahora como aportación
        elena = {"member_id": str(seed.elena.id), "amount": {"amount": "200.00", "currency": "EUR"}}
        assert elena in after["contributions"]

    def test_amount_date_and_fingerprint_never_change(self, as_raul, income) -> None:
        original = tx(as_raul, "Bizum de E M")
        r = patch(as_raul, original["id"], kind="expense", note="Era la cena  de grupo")
        t = r.json()["transaction"]
        assert (t["amount"], t["booked_at"], t["description"]) == (
            original["amount"],
            original["booked_at"],
            original["description"],
        )
        assert t["note"] == "Era la cena de grupo"

    def test_each_correction_leaves_a_history_row_with_its_author(
        self, as_raul, as_elena, seed, income
    ) -> None:
        bizum = tx_id(as_raul, "Bizum de E M")
        patch(as_raul, bizum, kind="contribution", member_id=str(seed.elena.id))
        patch(as_elena, bizum, note="Mi parte del alquiler")
        history = as_raul.get(f"/api/v1/transactions/{bizum}/history").json()
        assert [h["actor_id"] for h in history] == [str(seed.raul.id), str(seed.elena.id)]
        assert history[0]["summary"] == "Bizum de E M: Ingreso → Aportación de Elena"
        assert {(c["field"], c["before"], c["after"]) for c in history[0]["changes"]} == {
            ("kind", "income", "contribution"),
            ("member_id", None, str(seed.elena.id)),
        }
        assert history[1]["changes"] == [
            {
                "entity": "transaction",
                "field": "note",
                "before": "",
                "after": "Mi parte del alquiler",
            }
        ]

    def test_leaving_expense_drops_the_category_and_it_is_logged(self, as_raul) -> None:
        mercadona = tx_id(as_raul, "Mercadona")
        r = patch(as_raul, mercadona, kind="internal_transfer")
        assert r.json()["transaction"]["category_id"] is None
        fields = {
            c["field"]
            for c in as_raul.get(f"/api/v1/transactions/{mercadona}/history").json()[0]["changes"]
        }
        assert fields == {"kind", "category_id"}

    @pytest.mark.parametrize(
        "body",
        [
            {"kind": "contribution"},  # sin persona
            {"kind": "income", "member_id": "PARTNER"},  # persona sin aportación
            {"kind": "income", "category_id": "SUPER"},  # categoría sin gasto
            {"note": "x" * 501},
            {"note": "con\x00control"},
        ],
    )
    def test_invalid_corrections_are_422_and_change_nothing(self, as_raul, seed, body) -> None:
        body = {
            k: str(seed.elena.id)
            if v == "PARTNER"
            else category(as_raul, "super")
            if v == "SUPER"
            else v
            for k, v in body.items()
        }
        glovo = tx_id(as_raul, "Glovo")
        assert patch(as_raul, glovo, **body).status_code == 422
        assert as_raul.get(f"/api/v1/transactions/{glovo}/history").json() == []

    def test_contribution_from_someone_of_another_household_is_rejected(
        self, as_raul, seed
    ) -> None:
        r = patch(as_raul, tx_id(as_raul, "Glovo"), kind="contribution", member_id=str(seed.ana.id))
        assert r.status_code == 422


class TestPrivacy:
    def test_partner_cannot_edit_or_see_the_history_of_a_personal_account(
        self, as_raul, as_elena
    ) -> None:
        peluqueria = tx_id(as_elena, "Peluquería")
        assert patch(as_elena, peluqueria, note="Corte").status_code == 200
        assert patch(as_raul, peluqueria, note="Lo veo").status_code == 404
        assert as_raul.get(f"/api/v1/transactions/{peluqueria}/history").status_code == 404
        assert as_elena.get(f"/api/v1/transactions/{peluqueria}/history").status_code == 200

    def test_other_household_gets_404(self, as_raul, as_ana) -> None:
        mercadona = tx_id(as_raul, "Mercadona")
        assert patch(as_ana, mercadona, note="Hola").status_code == 404
        assert as_ana.get(f"/api/v1/transactions/{mercadona}/history").status_code == 404

    def test_only_the_author_can_undo_and_lists_only_their_operations(
        self, as_raul, as_elena, as_ana
    ) -> None:
        op = patch(as_raul, tx_id(as_raul, "Glovo"), note="Cena").json()["operation_id"]
        assert as_elena.post(f"/api/v1/changes/{op}/undo").status_code == 404
        assert as_ana.post(f"/api/v1/changes/{op}/undo").status_code == 404
        assert as_elena.get("/api/v1/changes").json() == []
        assert [o["id"] for o in as_raul.get("/api/v1/changes").json()] == [op]


class TestUndo:
    def test_undo_and_redo_a_correction(self, as_raul, seed, income) -> None:
        bizum = tx_id(as_raul, "Bizum de E M")
        op = patch(as_raul, bizum, kind="contribution", member_id=str(seed.elena.id)).json()[
            "operation_id"
        ]
        r = as_raul.post(f"/api/v1/changes/{op}/undo")
        assert r.status_code == 200
        assert (r.json()["applied"], r.json()["kept"]) == (2, 0)
        assert (tx(as_raul, "Bizum de E M")["kind"], tx(as_raul, "Bizum de E M")["member_id"]) == (
            "income",
            None,
        )
        assert as_raul.post(f"/api/v1/changes/{op}/undo").status_code == 409
        assert as_raul.post(f"/api/v1/changes/{op}/redo").status_code == 200
        assert tx(as_raul, "Bizum de E M")["kind"] == "contribution"
        assert as_raul.post(f"/api/v1/changes/{op}/redo").status_code == 409

    def test_undo_keeps_what_the_partner_changed_afterwards(self, as_raul, as_elena, seed) -> None:
        glovo = tx_id(as_raul, "Glovo")
        op = patch(
            as_raul, glovo, category_id=category(as_raul, "restaurantes"), learn=False
        ).json()["operation_id"]
        patch(as_elena, glovo, category_id=category(as_elena, "ocio"), learn=False)
        r = as_raul.post(f"/api/v1/changes/{op}/undo").json()
        assert (r["applied"], r["kept"], r["kept_by"]) == (0, 1, [str(seed.elena.id)])
        assert tx(as_raul, "Glovo")["category_id"] == category(as_raul, "ocio")

    def test_undoing_a_learned_rule_only_reverts_what_it_classified(
        self, as_raul, seed, session_factory
    ) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            for day, desc in ((9, "Bar Pepe"), (10, "BAR PEPE 1234"), (11, "Bar Pepe *55")):
                uow.transactions.add(_tx(seed.joint, "-12.00", desc, datetime(2026, 10, day, 21)))  # noqa: DTZ001
            uow.commit()
        rest = category(as_raul, "restaurantes")
        r = patch(as_raul, tx_id(as_raul, "Bar Pepe *55"), category_id=rest).json()
        assert r["also_categorized"] == 2
        # Uno de los que clasificó la regla se corrige después a mano: deshacer no lo toca.
        patch(
            as_raul,
            tx_id(as_raul, "BAR PEPE 1234"),
            category_id=category(as_raul, "ocio"),
            learn=False,
        )
        undo = as_raul.post(f"/api/v1/changes/{r['operation_id']}/undo").json()
        # El movimiento corregido, la regla y el otro que clasificó; se respeta el de la mano.
        assert (undo["applied"], undo["kept"]) == (3, 1)
        assert tx(as_raul, "Bar Pepe *55")["category_id"] is None
        assert tx(as_raul, "BAR PEPE 1234")["category_id"] == category(as_raul, "ocio")
        rows = as_raul.get("/api/v1/transactions", params={"q": "Bar Pepe"}).json()
        assert sorted(str(t["category_id"]) for t in rows) == sorted(
            ["None", "None", category(as_raul, "ocio")]
        )


def state(client) -> list[tuple]:
    rows = client.get("/api/v1/transactions").json()
    return sorted((t["id"], t["kind"], t["member_id"], t["category_id"], t["note"]) for t in rows)


@pytest.mark.parametrize("seed_value", range(12))
def test_undoing_every_operation_in_reverse_restores_the_initial_state(
    as_raul, as_elena, seed, income, seed_value
) -> None:
    """Propiedad (ADR-0017): para cualquier secuencia de correcciones de las dos personas,
    deshacer todas en orden inverso devuelve el estado inicial."""
    rng = random.Random(seed_value)
    initial = state(as_raul)
    shared = ["Mercadona", "Glovo", "Bizum de E M", "To pocket"]
    cats = [category(as_raul, s) for s in ("super", "restaurantes", "ocio")] + [None]
    people = [str(seed.raul.id), str(seed.elena.id)]
    done: list[tuple] = []
    for _ in range(rng.randint(3, 10)):
        who = rng.choice([as_raul, as_elena])
        target = tx_id(who, rng.choice(shared))
        body = rng.choice(
            [
                {"category_id": rng.choice(cats), "learn": rng.random() < 0.5, "kind": "expense"},
                {"kind": "contribution", "member_id": rng.choice(people)},
                {"kind": rng.choice(["income", "internal_transfer", "savings_transfer"])},
                {"note": rng.choice(["", "revisar", "cena"])},
            ]
        )
        r = patch(who, target, **body)
        if r.status_code == 200 and r.json()["operation_id"]:
            done.append((who, r.json()["operation_id"]))
    for who, op in reversed(done):
        assert who.post(f"/api/v1/changes/{op}/undo").json()["kept"] == 0
    assert state(as_raul) == initial
