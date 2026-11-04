"""OF-1101 y OF-1102: reglas con condiciones, vista previa y aplicar a lo existente."""

import pytest

from tests.db.test_imports_api import commit, upload


def cat(client, slug: str) -> str:
    return next(c["id"] for c in client.get("/api/v1/categories").json() if c["slug"] == slug)


def body(name="Glovo", conditions=None, actions=None, **extra) -> dict:
    return {
        "name": name,
        "conditions": conditions
        if conditions is not None
        else [{"field": "description", "op": "contains", "value": "glovo"}],
        "actions": actions
        if actions is not None
        else [{"type": "add_tags", "value": ["comida a domicilio"]}],
        **extra,
    }


def create(client, **kw):
    return client.post("/api/v1/automation-rules", json=body(**kw))


def tx(client, description: str, **params) -> dict:
    rows = client.get("/api/v1/transactions", params=params).json()
    return next(t for t in rows if t["description"] == description)


class TestCrud:
    def test_create_list_update_delete_with_undo(self, as_raul, seed) -> None:
        r = create(as_raul)
        assert r.status_code == 201
        rule = r.json()["rule"]
        assert (rule["phase"], rule["enabled"], rule["personal"], rule["priority"]) == (
            "normal",
            True,
            False,
            10,
        )
        assert [x["name"] for x in as_raul.get("/api/v1/automation-rules").json()] == ["Glovo"]

        changed = body(actions=[{"type": "add_tags", "value": ["domicilio"]}])
        up = as_raul.put(f"/api/v1/automation-rules/{rule['id']}", json=changed)
        assert up.status_code == 200 and up.json()["rule"]["actions"][0]["value"] == ["domicilio"]
        assert (
            as_raul.put(f"/api/v1/automation-rules/{rule['id']}", json=changed).json()[
                "operation_id"
            ]
            is None
        )

        assert (
            as_raul.post(f"/api/v1/changes/{up.json()['operation_id']}/undo").json()["applied"] == 1
        )
        assert as_raul.get("/api/v1/automation-rules").json()[0]["actions"][0]["value"] == [
            "comida a domicilio"
        ]

        gone = as_raul.delete(f"/api/v1/automation-rules/{rule['id']}").json()["operation_id"]
        assert as_raul.get("/api/v1/automation-rules").json() == []
        assert as_raul.post(f"/api/v1/changes/{gone}/undo").status_code == 200
        assert len(as_raul.get("/api/v1/automation-rules").json()) == 1
        # Deshacer la creación: la regla está como la dejó esa operación, así que se va entera.
        undone = as_raul.post(f"/api/v1/changes/{r.json()['operation_id']}/undo").json()
        assert undone["kept"] == 0 and as_raul.get("/api/v1/automation-rules").json() == []

    def test_priority_defaults_grow_and_phases_order_the_list(self, as_raul, seed) -> None:
        create(as_raul, name="A")
        create(as_raul, name="B", phase="before")
        create(as_raul, name="C", phase="after")
        create(as_raul, name="D")
        assert [r["name"] for r in as_raul.get("/api/v1/automation-rules").json()] == [
            "B",
            "A",
            "D",
            "C",
        ]

    def test_name_conflict_is_409(self, as_raul, seed) -> None:
        create(as_raul)
        assert create(as_raul, name="glovo").status_code == 409

    @pytest.mark.parametrize(
        "extra",
        [
            {"conditions": [{"field": "description", "op": "regex", "value": ".*"}]},
            {"conditions": [{"field": "description", "op": "contains", "value": ""}]},
            {"conditions": [{"field": "amount", "op": "between", "value": ["9", "1"]}]},
            {
                "actions": [
                    {"type": "set_category", "value": "00000000-0000-0000-0000-000000000000"}
                ]
            },
            {"actions": [{"type": "set_kind", "value": "contribution"}]},
            {"actions": [{"type": "add_tags", "value": ["a|b"]}]},
            {"conditions": []},
            {"actions": []},
            {"name": "   "},
        ],
    )
    def test_invalid_rules_are_422(self, as_raul, seed, extra) -> None:
        assert create(as_raul, **extra).status_code == 422
        assert as_raul.get("/api/v1/automation-rules").json() == []

    def test_a_hidden_category_cannot_be_used(self, as_raul, seed) -> None:
        c = cat(as_raul, "ropa")
        as_raul.patch(f"/api/v1/categories/{c}", json={"hidden": True})
        r = create(as_raul, actions=[{"type": "set_category", "value": c}])
        assert r.status_code == 422

    def test_requires_a_session(self, client, seed) -> None:
        assert client.get("/api/v1/automation-rules").status_code == 401


class TestPreviewAndApply:
    def test_preview_writes_nothing_and_apply_does_it_all_at_once(self, as_raul, seed) -> None:
        rest = cat(as_raul, "restaurantes")
        r = create(
            as_raul,
            actions=[
                {"type": "set_category", "value": rest},
                {"type": "add_tags", "value": ["domicilio"]},
                {"type": "set_note", "value": "Pedido"},
            ],
        ).json()["rule"]
        preview = as_raul.post(f"/api/v1/automation-rules/{r['id']}/preview").json()
        assert preview["count"] == 1
        assert {c["field"] for c in preview["items"][0]["changes"]} == {
            "category_id",
            "tags",
            "note",
        }
        assert tx(as_raul, "Glovo 50% dto")["category_id"] is None  # no ha escrito

        done = as_raul.post(f"/api/v1/automation-rules/{r['id']}/apply").json()
        assert done["changed"] == 1
        t = tx(as_raul, "Glovo 50% dto")
        assert (t["category_id"], t["tags"], t["note"]) == (rest, ["domicilio"], "Pedido")

        # Aplicar otra vez no cambia nada: es idempotente.
        again = as_raul.post(f"/api/v1/automation-rules/{r['id']}/apply").json()
        assert (again["changed"], again["operation_id"]) == (0, None)

        # Y todo se deshace de una vez.
        assert as_raul.post(f"/api/v1/changes/{done['operation_id']}/undo").json()["kept"] == 0
        t = tx(as_raul, "Glovo 50% dto")
        assert (t["category_id"], t["tags"], t["note"]) == (None, [], "")

    def test_the_draft_preview_does_not_need_saving(self, as_raul, seed) -> None:
        p = as_raul.post("/api/v1/automation-rules/preview", json=body()).json()
        assert p["count"] == 1 and as_raul.get("/api/v1/automation-rules").json() == []

    def test_never_overrides_a_category_already_set_nor_reviewed_nor_split(
        self, as_raul, seed
    ) -> None:
        rest, hogar = cat(as_raul, "restaurantes"), cat(as_raul, "hogar")
        rule = create(
            as_raul,
            conditions=[{"field": "description", "op": "contains", "value": "mercadona"}],
            actions=[{"type": "set_category", "value": rest}],
        ).json()["rule"]
        # Mercadona ya tiene categoría (Supermercado): no se pisa.
        assert as_raul.post(f"/api/v1/automation-rules/{rule['id']}/preview").json()["count"] == 0
        # Glovo: revisado → no se toca; dividido → no se toca.
        glovo = tx(as_raul, "Glovo 50% dto")["id"]
        glovo_rule = create(as_raul, name="G").json()["rule"]
        as_raul.post("/api/v1/transactions/review", json={"ids": [glovo], "reviewed": True})
        assert (
            as_raul.post(f"/api/v1/automation-rules/{glovo_rule['id']}/preview").json()["count"]
            == 0
        )
        as_raul.post("/api/v1/transactions/review", json={"ids": [glovo], "reviewed": False})
        as_raul.put(
            f"/api/v1/transactions/{glovo}/split",
            json={
                "parts": [
                    {"amount": "-20.00", "category_id": rest},
                    {"amount": "-5.40", "category_id": hogar},
                ]
            },
        )
        assert (
            as_raul.post(f"/api/v1/automation-rules/{glovo_rule['id']}/preview").json()["count"]
            == 0
        )

    def test_set_kind_only_changes_generic_kinds(self, as_raul, seed) -> None:
        r = create(
            as_raul,
            conditions=[{"field": "description", "op": "contains", "value": "to pocket"}],
            actions=[{"type": "set_kind", "value": "internal_transfer"}],
        ).json()["rule"]
        # «To pocket» ya es un traspaso a hucha: lo fijó el importador y no se toca.
        assert as_raul.post(f"/api/v1/automation-rules/{r['id']}/preview").json()["count"] == 0
        g = create(
            as_raul,
            name="Glovo traspaso",
            actions=[{"type": "set_kind", "value": "income"}],
        ).json()["rule"]
        assert as_raul.post(f"/api/v1/automation-rules/{g['id']}/apply").json()["changed"] == 1
        assert tx(as_raul, "Glovo 50% dto")["kind"] == "income"

    def test_condition_by_amount_and_direction(self, as_raul, seed) -> None:
        r = create(
            as_raul,
            conditions=[
                {"field": "direction", "op": "is", "value": "expense"},
                {"field": "amount", "op": "between", "value": ["80", "100"]},
            ],
            actions=[{"type": "add_tags", "value": ["compra grande"]}],
        ).json()["rule"]
        p = as_raul.post(f"/api/v1/automation-rules/{r['id']}/preview").json()
        assert [i["transaction"]["description"] for i in p["items"]] == ["Mercadona"]


class TestPrivacy:
    def test_personal_rules_are_invisible_to_the_partner(self, as_raul, as_elena, seed) -> None:
        mine = create(as_raul, name="Mía", personal=True).json()["rule"]
        assert as_elena.get("/api/v1/automation-rules").json() == []
        for call in (
            lambda: as_elena.put(f"/api/v1/automation-rules/{mine['id']}", json=body(name="X")),
            lambda: as_elena.delete(f"/api/v1/automation-rules/{mine['id']}"),
            lambda: as_elena.post(f"/api/v1/automation-rules/{mine['id']}/preview"),
            lambda: as_elena.post(f"/api/v1/automation-rules/{mine['id']}/apply"),
        ):
            assert call().status_code == 404
        assert [r["name"] for r in as_raul.get("/api/v1/automation-rules").json()] == ["Mía"]

    def test_household_rules_are_seen_by_both_but_only_touch_what_each_sees(
        self, as_raul, as_elena, seed
    ) -> None:
        # Una regla del hogar sobre «Peluquería» (cuenta personal de Elena).
        rule = create(
            as_raul,
            name="Pelu",
            conditions=[{"field": "description", "op": "contains", "value": "peluquer"}],
        ).json()["rule"]
        assert as_raul.post(f"/api/v1/automation-rules/{rule['id']}/preview").json()["count"] == 0
        assert as_elena.post(f"/api/v1/automation-rules/{rule['id']}/preview").json()["count"] == 1
        assert as_raul.post(f"/api/v1/automation-rules/{rule['id']}/apply").json()["changed"] == 0
        assert tx(as_elena, "Peluquería")["tags"] == []
        assert as_elena.post(f"/api/v1/automation-rules/{rule['id']}/apply").json()["changed"] == 1
        assert tx(as_elena, "Peluquería")["tags"] == ["comida a domicilio"]

    def test_a_household_rule_cannot_name_a_personal_account(self, as_raul, seed) -> None:
        c = [{"field": "account", "op": "in", "value": [str(seed.raul_personal.id)]}]
        assert create(as_raul, conditions=c).status_code == 422
        assert create(as_raul, conditions=c, personal=True).status_code == 201

    def test_a_rule_cannot_name_an_account_you_cannot_see(self, as_raul, seed) -> None:
        c = [{"field": "account", "op": "in", "value": [str(seed.elena_personal.id)]}]
        assert create(as_raul, conditions=c, personal=True).status_code == 422

    def test_a_personal_rule_only_reaches_its_owners_personal_accounts(self, as_raul, seed) -> None:
        r = create(as_raul, name="P", personal=True).json()["rule"]
        # «Glovo» está en la conjunta: una regla personal no llega.
        assert as_raul.post(f"/api/v1/automation-rules/{r['id']}/preview").json()["count"] == 0

    def test_other_households_get_404(self, as_ana, as_raul, seed) -> None:
        r = create(as_raul).json()["rule"]
        assert as_ana.post(f"/api/v1/automation-rules/{r['id']}/apply").status_code == 404
        assert as_ana.get("/api/v1/automation-rules").json() == []

    def test_the_partners_undo_of_a_rule_is_404(self, as_raul, as_elena, seed) -> None:
        op = create(as_raul).json()["operation_id"]
        assert as_elena.post(f"/api/v1/changes/{op}/undo").status_code == 404


class TestPriority:
    def test_the_first_rule_that_sets_a_field_wins_and_the_rest_still_add(
        self, as_raul, seed
    ) -> None:
        rest, hogar = cat(as_raul, "restaurantes"), cat(as_raul, "hogar")
        create(
            as_raul,
            name="Segunda",
            priority=20,
            actions=[
                {"type": "set_category", "value": hogar},
                {"type": "add_tags", "value": ["dos"]},
            ],
        )
        first = create(
            as_raul, name="Primera", priority=5, actions=[{"type": "set_category", "value": rest}]
        ).json()["rule"]
        p1 = as_raul.post(f"/api/v1/automation-rules/{first['id']}/apply").json()
        assert p1["changed"] == 1
        second = next(
            r for r in as_raul.get("/api/v1/automation-rules").json() if r["name"] == "Segunda"
        )
        as_raul.post(f"/api/v1/automation-rules/{second['id']}/apply")
        t = tx(as_raul, "Glovo 50% dto")
        assert (t["category_id"], t["tags"]) == (rest, ["dos"])  # la categoría la fijó la primera


class TestImport:
    def test_rules_classify_rows_in_the_preview_and_when_confirming(self, as_raul, seed) -> None:
        rest = cat(as_raul, "restaurantes")
        create(
            as_raul,
            name="Café",
            conditions=[{"field": "description", "op": "contains", "value": "mercadona"}],
            actions=[
                {"type": "set_category", "value": rest},
                {"type": "add_tags", "value": ["importado"]},
                {"type": "set_note", "value": "por regla"},
            ],
        )
        preview = upload(as_raul, seed.joint.id).json()
        rows = [r for r in preview["rows"] if "Mercadona" in r["description"]]
        assert rows and all(r["category_id"] == rest and r["tags"] == ["importado"] for r in rows)
        assert commit(as_raul, preview["id"]).status_code == 200
        imported = [
            t
            for t in as_raul.get(
                "/api/v1/transactions", params={"account_id": str(seed.joint.id)}
            ).json()
            if t["source"].startswith("import:") and "Mercadona" in t["description"]
        ]
        assert imported
        assert all(
            t["category_id"] == rest and t["tags"] == ["importado"] and t["note"] == "por regla"
            for t in imported
        )

    def test_the_learned_rule_still_works_when_no_explicit_rule_matches(
        self, as_raul, seed
    ) -> None:
        create(
            as_raul,
            name="Otra",
            conditions=[{"field": "description", "op": "contains", "value": "zzz"}],
        )
        preview = upload(as_raul, seed.joint.id).json()
        assert preview["new_count"] > 0

    def test_an_explicit_rule_beats_the_learned_one(self, as_raul, seed) -> None:
        # Se aprende «Mercadona → Supermercado» al categorizar; una regla explícita manda.
        rest = cat(as_raul, "restaurantes")
        m = tx(as_raul, "Mercadona", month="2026-10")["id"]
        as_raul.patch(f"/api/v1/transactions/{m}", json={"category_id": cat(as_raul, "super")})
        create(
            as_raul,
            name="Manda",
            conditions=[{"field": "description", "op": "contains", "value": "mercadona"}],
            actions=[{"type": "set_category", "value": rest}],
        )
        preview = upload(as_raul, seed.joint.id).json()
        rows = [
            r for r in preview["rows"] if "Mercadona" in r["description"] and not r["duplicate"]
        ]
        assert rows and all(r["category_id"] == rest for r in rows)
