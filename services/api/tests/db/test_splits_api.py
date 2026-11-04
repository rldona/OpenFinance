"""OF-1003: dividir un gasto en partes con categoría."""

import pytest


def category(client, slug: str) -> str:
    return next(c["id"] for c in client.get("/api/v1/categories").json() if c["slug"] == slug)


def tx(client, description: str, **params) -> dict:
    rows = client.get("/api/v1/transactions", params=params).json()
    return next(t for t in rows if t["description"] == description)


def split(client, transaction_id: str, parts: list[tuple[str, str]]):
    return client.put(
        f"/api/v1/transactions/{transaction_id}/split",
        json={"parts": [{"amount": a, "category_id": c} for a, c in parts]},
    )


def month(client, name: str = "2026-10") -> dict:
    return client.get("/api/v1/insights/month", params={"month": name}).json()


def by_category(overview: dict) -> dict[str, str]:
    return {c["category_id"]: c["amount"]["amount"] for c in overview["categories"]}


@pytest.fixture
def cats(as_raul):
    return {
        "super": category(as_raul, "super"),
        "restaurantes": category(as_raul, "restaurantes"),
        "hogar": category(as_raul, "hogar"),
    }


class TestSplit:
    def test_splits_a_receipt_and_reports_count_the_parts(self, as_raul, seed, cats) -> None:
        before = month(as_raul)
        glovo = tx(as_raul, "Glovo 50% dto")  # -25.40, sin categoría
        r = split(
            as_raul, glovo["id"], [("-20.00", cats["restaurantes"]), ("-5.40", cats["hogar"])]
        )
        assert r.status_code == 200
        out = r.json()["transaction"]
        assert [p["amount"]["amount"] for p in out["parts"]] == ["-20.00", "-5.40"]
        assert out["amount"]["amount"] == "-25.40"  # el movimiento no cambia
        after = month(as_raul)
        # El total del mes no cambia: dividir solo reparte entre categorías.
        assert after["spent"] == before["spent"]
        got = by_category(after)
        assert got[cats["restaurantes"]] == "20.00" and got[cats["hogar"]] == "5.40"

    def test_a_split_expense_counts_as_categorized(self, as_raul, seed, cats) -> None:
        pending = as_raul.get("/api/v1/transactions/uncategorized-count").json()["count"]
        glovo = tx(as_raul, "Glovo 50% dto")
        split(as_raul, glovo["id"], [("-20.00", cats["restaurantes"]), ("-5.40", cats["hogar"])])
        assert (
            as_raul.get("/api/v1/transactions/uncategorized-count").json()["count"] == pending - 1
        )
        listed = as_raul.get("/api/v1/transactions", params={"uncategorized": "true"}).json()
        assert "Glovo 50% dto" not in {t["description"] for t in listed}

    def test_filtering_by_a_part_category_finds_it(self, as_raul, seed, cats) -> None:
        glovo = tx(as_raul, "Glovo 50% dto")
        split(as_raul, glovo["id"], [("-20.00", cats["restaurantes"]), ("-5.40", cats["hogar"])])
        found = as_raul.get("/api/v1/transactions", params={"category_id": cats["hogar"]}).json()
        assert [t["description"] for t in found] == ["Glovo 50% dto"]

    def test_splitting_a_categorized_one_moves_the_category_to_the_parts(
        self, as_raul, seed, cats
    ) -> None:
        mercadona = next(
            t
            for t in as_raul.get("/api/v1/transactions", params={"month": "2026-10"}).json()
            if t["description"] == "Mercadona"
        )
        before = by_category(month(as_raul))[cats["super"]]
        assert before == "87.34"
        r = split(as_raul, mercadona["id"], [("-60.00", cats["super"]), ("-27.34", cats["hogar"])])
        assert r.json()["transaction"]["category_id"] is None
        got = by_category(month(as_raul))
        assert got[cats["super"]] == "60.00" and got[cats["hogar"]] == "27.34"

    def test_undo_restores_the_category_and_the_reports(self, as_raul, seed, cats) -> None:
        mercadona = next(
            t
            for t in as_raul.get("/api/v1/transactions", params={"month": "2026-10"}).json()
            if t["description"] == "Mercadona"
        )
        op = split(
            as_raul, mercadona["id"], [("-60.00", cats["super"]), ("-27.34", cats["hogar"])]
        ).json()["operation_id"]
        assert as_raul.post(f"/api/v1/changes/{op}/undo").json()["applied"] == 2
        assert by_category(month(as_raul))[cats["super"]] == "87.34"
        refreshed = tx(as_raul, "Mercadona", month="2026-10")
        assert refreshed["parts"] == [] and refreshed["category_id"] == cats["super"]
        assert as_raul.post(f"/api/v1/changes/{op}/redo").status_code == 200
        assert by_category(month(as_raul))[cats["hogar"]] == "27.34"

    def test_unsplit(self, as_raul, seed, cats) -> None:
        glovo = tx(as_raul, "Glovo 50% dto")
        split(as_raul, glovo["id"], [("-20.00", cats["restaurantes"]), ("-5.40", cats["hogar"])])
        r = as_raul.delete(f"/api/v1/transactions/{glovo['id']}/split")
        assert r.status_code == 200 and r.json()["transaction"]["parts"] == []
        assert as_raul.post(f"/api/v1/changes/{r.json()['operation_id']}/undo").status_code == 200
        assert len(tx(as_raul, "Glovo 50% dto")["parts"]) == 2
        assert (
            as_raul.delete(
                f"/api/v1/transactions/{tx(as_raul, 'Mercadona')['id']}/split"
            ).status_code
            == 422
        )

    def test_resplitting_replaces_the_parts(self, as_raul, seed, cats) -> None:
        glovo = tx(as_raul, "Glovo 50% dto")
        split(as_raul, glovo["id"], [("-20.00", cats["restaurantes"]), ("-5.40", cats["hogar"])])
        split(as_raul, glovo["id"], [("-10.00", cats["super"]), ("-15.40", cats["hogar"])])
        assert [p["amount"]["amount"] for p in tx(as_raul, "Glovo 50% dto")["parts"]] == [
            "-10.00",
            "-15.40",
        ]

    @pytest.mark.parametrize(
        "parts",
        [
            [("-20.00", "restaurantes"), ("-5.00", "hogar")],  # suman 25.00, no 25.40
            [("-20.00", "restaurantes")],  # una sola parte
            [("-30.00", "restaurantes"), ("4.60", "hogar")],  # una parte con otro signo
            [("-25.40", "restaurantes"), ("0.00", "hogar")],  # una parte de cero
        ],
    )
    def test_invalid_splits_are_422_and_change_nothing(self, as_raul, seed, cats, parts) -> None:
        glovo = tx(as_raul, "Glovo 50% dto")
        body = [{"amount": a, "category_id": cats[c]} for a, c in parts]
        r = as_raul.put(f"/api/v1/transactions/{glovo['id']}/split", json={"parts": body})
        assert r.status_code == 422
        assert tx(as_raul, "Glovo 50% dto")["parts"] == []

    def test_only_expenses_can_be_split(self, as_raul, seed, cats) -> None:
        payment = tx(as_raul, "Payment from Raul")
        r = split(as_raul, payment["id"], [("800.00", cats["super"]), ("800.00", cats["hogar"])])
        assert r.status_code == 422

    def test_a_split_expense_refuses_a_new_category_or_a_new_kind(
        self, as_raul, seed, cats
    ) -> None:
        glovo = tx(as_raul, "Glovo 50% dto")
        split(as_raul, glovo["id"], [("-20.00", cats["restaurantes"]), ("-5.40", cats["hogar"])])
        assert (
            as_raul.patch(
                f"/api/v1/transactions/{glovo['id']}", json={"category_id": cats["super"]}
            ).status_code
            == 422
        )
        assert (
            as_raul.patch(
                f"/api/v1/transactions/{glovo['id']}", json={"kind": "income"}
            ).status_code
            == 422
        )
        assert (
            as_raul.patch(f"/api/v1/transactions/{glovo['id']}", json={"note": "ok"}).status_code
            == 200
        )

    def test_a_hidden_or_unknown_category_is_rejected(self, as_raul, seed, cats) -> None:
        glovo = tx(as_raul, "Glovo 50% dto")
        r = split(
            as_raul,
            glovo["id"],
            [("-20.00", cats["super"]), ("-5.40", "00000000-0000-0000-0000-000000000000")],
        )
        assert r.status_code == 404

    def test_balances_are_unchanged(self, as_raul, seed, cats) -> None:
        before = {a["name"]: a["balance"] for a in as_raul.get("/api/v1/accounts").json()}
        glovo = tx(as_raul, "Glovo 50% dto")
        split(as_raul, glovo["id"], [("-20.00", cats["restaurantes"]), ("-5.40", cats["hogar"])])
        after = {a["name"]: a["balance"] for a in as_raul.get("/api/v1/accounts").json()}
        assert before == after


class TestPrivacy:
    def test_cannot_split_the_partners_personal_expense(
        self, as_raul, as_elena, seed, cats
    ) -> None:
        pelu = tx(as_elena, "Peluquería")
        r = split(as_raul, pelu["id"], [("-20.00", cats["super"]), ("-22.00", cats["hogar"])])
        assert r.status_code == 404
        assert (
            split(
                as_elena, pelu["id"], [("-20.00", cats["super"]), ("-22.00", cats["hogar"])]
            ).status_code
            == 200
        )

    def test_partner_cannot_see_those_parts_in_my_reports(
        self, as_raul, as_elena, seed, cats
    ) -> None:
        pelu = tx(as_elena, "Peluquería")
        split(as_elena, pelu["id"], [("-20.00", cats["super"]), ("-22.00", cats["hogar"])])
        # La vista del hogar de Raúl no cuenta cuentas personales.
        assert by_category(month(as_raul)).get(cats["hogar"]) is None

    def test_other_households_get_404(self, as_ana, as_raul, seed, cats) -> None:
        glovo = tx(as_raul, "Glovo 50% dto")
        assert as_ana.delete(f"/api/v1/transactions/{glovo['id']}/split").status_code == 404


def test_the_export_carries_the_parts(as_raul, seed, cats) -> None:
    glovo = tx(as_raul, "Glovo 50% dto")
    split(as_raul, glovo["id"], [("-20.00", cats["restaurantes"]), ("-5.40", cats["hogar"])])
    data = as_raul.get("/api/v1/export", params={"format": "json"}).json()
    row = next(t for t in data["transactions"] if t["description"] == "Glovo 50% dto")
    assert row["parts"] == "Restaurantes:-20.00|Hogar:-5.40"
    assert row["amount"] == "-25.40"
