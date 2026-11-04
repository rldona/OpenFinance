"""Reglas visibles: listar, borrar y no aprender de personas (OF-702)."""

from datetime import datetime

from openfinance.infrastructure.db.repositories import SqlUnitOfWork

from .conftest import _tx
from .test_changes_api import category, patch, tx, tx_id


def rules(client) -> list[dict]:
    return client.get("/api/v1/rules").json()


class TestList:
    def test_household_and_own_personal_rules_with_their_matches(
        self, as_raul, as_elena, as_ana
    ) -> None:
        patch(as_raul, tx_id(as_raul, "Mercadona"), category_id=category(as_raul, "super"))
        patch(as_elena, tx_id(as_elena, "Peluquería"), category_id=category(as_elena, "otros"))
        mine = rules(as_elena)
        assert [(r["merchant"], r["scope"]) for r in mine] == [
            ("Mercadona", "household"),
            ("Peluqueria", "personal"),
        ]
        assert mine[0]["matches"] == 2  # los dos Mercadona de la conjunta
        assert mine[1]["matches"] == 1
        # La pareja ve la del hogar, pero no la personal de Elena; otro hogar no ve nada.
        assert [r["merchant"] for r in rules(as_raul)] == ["Mercadona"]
        assert rules(as_ana) == []


class TestDelete:
    def test_delete_keeps_classified_movements_and_can_be_undone(self, as_raul) -> None:
        patch(as_raul, tx_id(as_raul, "Glovo"), category_id=category(as_raul, "restaurantes"))
        key = rules(as_raul)[0]["key"]
        r = as_raul.delete(f"/api/v1/rules/household/{key}")
        assert r.status_code == 200
        assert rules(as_raul) == []
        assert tx(as_raul, "Glovo")["category_id"] == category(as_raul, "restaurantes")
        as_raul.post(f"/api/v1/changes/{r.json()['operation_id']}/undo")
        assert [x["key"] for x in rules(as_raul)] == [key]

    def test_cannot_delete_the_partner_personal_rule(self, as_raul, as_elena, as_ana) -> None:
        patch(as_elena, tx_id(as_elena, "Peluquería"), category_id=category(as_elena, "otros"))
        key = rules(as_elena)[0]["key"]
        assert as_raul.delete(f"/api/v1/rules/personal/{key}").status_code == 404
        assert as_raul.delete(f"/api/v1/rules/household/{key}").status_code == 404
        assert as_ana.delete(f"/api/v1/rules/personal/{key}").status_code == 404
        assert len(rules(as_elena)) == 1

    def test_unknown_scope_is_422(self, as_raul) -> None:
        assert as_raul.delete("/api/v1/rules/otro/MERCADONA").status_code == 422


class TestPeopleDoNotLearn:
    def test_bizum_and_transfers_do_not_learn_rules(self, as_raul, seed, session_factory) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            for day, desc in ((12, "Bizum a Juan Perez"), (13, "Bizum a Juan Perez cena")):
                uow.transactions.add(_tx(seed.joint, "-20.00", desc, datetime(2026, 10, day, 20)))  # noqa: DTZ001
            uow.commit()
        r = patch(
            as_raul,
            tx_id(as_raul, "Bizum a Juan Perez cena"),
            category_id=category(as_raul, "ocio"),
        )
        assert (r.json()["rule"], r.json()["also_categorized"]) == (None, 0)
        assert rules(as_raul) == []
        both = as_raul.get("/api/v1/transactions", params={"q": "Bizum a Juan"}).json()
        assert sorted(str(t["category_id"]) for t in both) == sorted(
            ["None", category(as_raul, "ocio")]
        )
