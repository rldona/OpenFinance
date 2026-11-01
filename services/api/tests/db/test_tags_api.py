"""OF-1002: etiquetas y notas largas, con privacidad y deshacer."""

import pytest

from openfinance.domain.ledger import normalize_note
from openfinance.domain.tags import TagError, clean_tags


def tx_id(client, description: str) -> str:
    rows = client.get("/api/v1/transactions").json()
    return next(t["id"] for t in rows if t["description"] == description)


def put_tags(client, transaction_id: str, tags: list[str]):
    return client.put(f"/api/v1/transactions/{transaction_id}/tags", json={"tags": tags})


def tags_of(client, description: str) -> list[str]:
    rows = client.get("/api/v1/transactions").json()
    return next(t["tags"] for t in rows if t["description"] == description)


class TestCleanTags:
    def test_trims_dedupes_ignoring_case_and_sorts(self) -> None:
        assert clean_tags(["  #Viaje ", "viaje", "Regalos", "casa  nueva"]) == (
            "casa nueva",
            "Regalos",
            "Viaje",
        )

    @pytest.mark.parametrize("bad", ["", "   ", "#", "a|b", "x" * 41, "con\x00control"])
    def test_rejects(self, bad) -> None:
        with pytest.raises(TagError):
            clean_tags([bad])

    def test_at_most_ten(self) -> None:
        with pytest.raises(TagError):
            clean_tags([f"t{i}" for i in range(11)])


class TestSetTags:
    def test_sets_and_lists_them_on_the_movement(self, as_raul, seed) -> None:
        r = put_tags(as_raul, tx_id(as_raul, "Glovo 50% dto"), ["Cena", "#Amigos"])
        assert r.status_code == 200
        assert r.json()["transaction"]["tags"] == ["Amigos", "Cena"]
        assert tags_of(as_raul, "Glovo 50% dto") == ["Amigos", "Cena"]
        assert as_raul.get("/api/v1/tags").json() == [
            {"tag": "Amigos", "count": 1},
            {"tag": "Cena", "count": 1},
        ]

    def test_undo_and_redo(self, as_raul, seed) -> None:
        t = tx_id(as_raul, "Glovo 50% dto")
        op = put_tags(as_raul, t, ["Cena"]).json()["operation_id"]
        op2 = put_tags(as_raul, t, ["Cena", "Amigos"]).json()["operation_id"]
        assert as_raul.post(f"/api/v1/changes/{op2}/undo").json()["applied"] == 1
        assert tags_of(as_raul, "Glovo 50% dto") == ["Cena"]
        assert as_raul.post(f"/api/v1/changes/{op}/undo").status_code == 200
        assert tags_of(as_raul, "Glovo 50% dto") == []
        assert as_raul.post(f"/api/v1/changes/{op}/redo").status_code == 200
        assert tags_of(as_raul, "Glovo 50% dto") == ["Cena"]

    def test_undo_respects_a_later_change_by_the_partner(self, as_raul, as_elena, seed) -> None:
        t = tx_id(as_raul, "Glovo 50% dto")
        op = put_tags(as_raul, t, ["Cena"]).json()["operation_id"]
        put_tags(as_elena, t, ["Cena", "Elena"])
        undone = as_raul.post(f"/api/v1/changes/{op}/undo").json()
        assert (undone["applied"], undone["kept"]) == (0, 1)
        assert tags_of(as_raul, "Glovo 50% dto") == ["Cena", "Elena"]

    def test_no_change_makes_no_operation(self, as_raul, seed) -> None:
        t = tx_id(as_raul, "Glovo 50% dto")
        put_tags(as_raul, t, ["Cena"])
        assert put_tags(as_raul, t, ["#Cena"]).json()["operation_id"] is None

    def test_clearing_them(self, as_raul, seed) -> None:
        t = tx_id(as_raul, "Glovo 50% dto")
        put_tags(as_raul, t, ["Cena"])
        assert put_tags(as_raul, t, []).json()["transaction"]["tags"] == []
        assert as_raul.get("/api/v1/tags").json() == []

    @pytest.mark.parametrize("tags", [["a|b"], ["x" * 41], [f"t{i}" for i in range(10)] + ["más"]])
    def test_invalid_is_422_and_changes_nothing(self, as_raul, seed, tags) -> None:
        t = tx_id(as_raul, "Glovo 50% dto")
        assert put_tags(as_raul, t, tags).status_code == 422
        assert tags_of(as_raul, "Glovo 50% dto") == []


class TestFilterAndPrivacy:
    def test_filters_the_list_and_the_page_by_tag_ignoring_case(self, as_raul, seed) -> None:
        put_tags(as_raul, tx_id(as_raul, "Glovo 50% dto"), ["Cena"])
        found = as_raul.get("/api/v1/transactions", params={"tag": "CENA"}).json()
        assert [t["description"] for t in found] == ["Glovo 50% dto"]
        page = as_raul.get("/api/v1/transactions/page", params={"tag": "cena"}).json()
        assert (page["count"], page["items"][0]["description"]) == (1, "Glovo 50% dto")
        assert as_raul.get("/api/v1/transactions", params={"tag": "otra"}).json() == []

    def test_the_partner_cannot_see_or_set_tags_on_a_personal_account(
        self, as_raul, as_elena, seed
    ) -> None:
        pelu = tx_id(as_elena, "Peluquería")
        assert put_tags(as_elena, pelu, ["Personal"]).status_code == 200
        assert put_tags(as_raul, pelu, ["Mía"]).status_code == 404
        assert {t["tag"] for t in as_raul.get("/api/v1/tags").json()} == set()
        assert as_raul.get("/api/v1/transactions", params={"tag": "Personal"}).json() == []
        assert [t["tag"] for t in as_elena.get("/api/v1/tags").json()] == ["Personal"]

    def test_counts_only_what_you_see(self, as_raul, as_elena, seed) -> None:
        put_tags(as_raul, tx_id(as_raul, "Glovo 50% dto"), ["Cena"])
        put_tags(as_elena, tx_id(as_elena, "Peluquería"), ["cena"])
        assert as_raul.get("/api/v1/tags").json() == [{"tag": "Cena", "count": 1}]
        assert as_elena.get("/api/v1/tags").json()[0]["count"] == 2

    def test_other_households_get_404(self, as_ana, as_raul, seed) -> None:
        assert put_tags(as_ana, tx_id(as_raul, "Glovo 50% dto"), ["x"]).status_code == 404

    def test_partners_undo_of_tags_is_404_for_you(self, as_raul, as_elena, seed) -> None:
        op = put_tags(as_elena, tx_id(as_elena, "Glovo 50% dto"), ["Cena"]).json()["operation_id"]
        assert as_raul.post(f"/api/v1/changes/{op}/undo").status_code == 404


class TestExport:
    def test_export_carries_the_tags_of_what_you_see(self, as_raul, as_elena, seed) -> None:
        put_tags(as_raul, tx_id(as_raul, "Glovo 50% dto"), ["Cena", "Amigos"])
        put_tags(as_elena, tx_id(as_elena, "Peluquería"), ["Privada"])
        data = as_raul.get("/api/v1/export", params={"format": "json"}).json()
        by_description = {t["description"]: t["tags"] for t in data["transactions"]}
        assert by_description["Glovo 50% dto"] == "Amigos|Cena"
        assert "Peluquería" not in by_description
        assert "Privada" not in str(data)


class TestLongNotes:
    def test_normalize_keeps_lines_but_cleans_spaces_and_blank_runs(self) -> None:
        assert normalize_note("  uno   dos \r\n\r\n\r\n tres  \n") == "uno dos\n\ntres"
        assert normalize_note("\n\n") == ""

    def test_a_long_multiline_note_is_saved_and_shown(self, as_raul, seed) -> None:
        t = tx_id(as_raul, "Glovo 50% dto")
        note = ("Línea con detalle.\n" * 100).strip()
        assert len(note) > 500
        r = as_raul.patch(f"/api/v1/transactions/{t}", json={"note": note})
        assert r.status_code == 200
        assert r.json()["transaction"]["note"] == note

    def test_over_2000_is_rejected(self, as_raul, seed) -> None:
        t = tx_id(as_raul, "Glovo 50% dto")
        assert (
            as_raul.patch(f"/api/v1/transactions/{t}", json={"note": "x" * 2001}).status_code == 422
        )
