"""OF-102 y OF-103: cuentas, movimientos, privacidad y aislamiento entre hogares."""


def names(accounts):
    return {a["name"]: a for a in accounts}


class TestAccounts:
    def test_each_person_sees_joint_and_only_their_personal_account(
        self, as_raul, as_elena
    ) -> None:
        assert [a["name"] for a in as_raul.get("/api/v1/accounts").json()] == [
            "Cuenta conjunta",
            "Bankinter Raúl",
        ]
        assert set(names(as_elena.get("/api/v1/accounts").json())) == {
            "Cuenta conjunta",
            "Bankinter Elena",
        }

    def test_balances_are_exact(self, as_raul) -> None:
        accounts = names(as_raul.get("/api/v1/accounts").json())
        # 100 + 1600 - 300 - 87.34 - 25.40 - 60
        assert accounts["Cuenta conjunta"]["balance"] == {"amount": "1227.26", "currency": "EUR"}
        assert accounts["Bankinter Raúl"]["balance"]["amount"] == "-1100.00"
        assert accounts["Bankinter Raúl"]["kind"] == "personal"
        assert accounts["Cuenta conjunta"]["institution"] == "revolut"

    def test_other_household_sees_only_its_own(self, as_ana) -> None:
        assert set(names(as_ana.get("/api/v1/accounts").json())) == {"Su conjunta"}


class TestTransactions:
    def test_month_filter_and_order(self, as_raul) -> None:
        rows = as_raul.get("/api/v1/transactions", params={"month": "2026-10"}).json()
        assert [r["description"] for r in rows] == [
            "Glovo 50% dto",
            "Mercadona",
            "To pocket Ahorro",
            "Payment from Raul",
            "Aportación casa",
        ]

    def test_amounts_and_kinds(self, as_raul) -> None:
        rows = as_raul.get("/api/v1/transactions", params={"month": "2026-10"}).json()
        pocket = next(r for r in rows if r["description"] == "To pocket Ahorro")
        assert pocket["kind"] == "savings_transfer"
        assert pocket["amount"] == {"amount": "-300.00", "currency": "EUR"}
        contribution = next(r for r in rows if r["description"] == "Payment from Raul")
        assert contribution["member_id"] is not None

    def test_text_search_is_case_insensitive_and_escapes_wildcards(self, as_raul) -> None:
        assert len(as_raul.get("/api/v1/transactions", params={"q": "mercadona"}).json()) == 2
        assert len(as_raul.get("/api/v1/transactions", params={"q": "50%"}).json()) == 1
        assert as_raul.get("/api/v1/transactions", params={"q": "%"}).json() != []
        assert as_raul.get("/api/v1/transactions", params={"q": "_"}).json() == []

    def test_uncategorized_only_returns_expenses_without_category(self, as_raul) -> None:
        rows = as_raul.get("/api/v1/transactions", params={"uncategorized": "true"}).json()
        assert [r["description"] for r in rows] == ["Glovo 50% dto"]

    def test_filter_by_account(self, as_raul, seed) -> None:
        rows = as_raul.get(
            "/api/v1/transactions", params={"account_id": str(seed.raul_personal.id)}
        ).json()
        assert [r["description"] for r in rows] == ["Aportación casa"]

    def test_invalid_month(self, as_raul) -> None:
        for bad in ("2026-13", "26-10", "octubre"):
            r = as_raul.get("/api/v1/transactions", params={"month": bad})
            assert r.status_code == 422


class TestPrivacyAndIsolation:
    def test_personal_movements_of_partner_are_hidden(self, as_raul) -> None:
        rows = as_raul.get("/api/v1/transactions").json()
        assert "Peluquería" not in {r["description"] for r in rows}

    def test_partner_personal_account_cannot_be_requested_by_id(self, as_raul, seed) -> None:
        r = as_raul.get("/api/v1/transactions", params={"account_id": str(seed.elena_personal.id)})
        assert r.status_code == 404

    def test_other_household_account_cannot_be_requested_by_id(self, as_raul, seed) -> None:
        r = as_raul.get("/api/v1/transactions", params={"account_id": str(seed.other_joint.id)})
        assert r.status_code == 404

    def test_other_household_data_never_leaks(self, as_raul, as_ana) -> None:
        mine = {r["description"] for r in as_raul.get("/api/v1/transactions").json()}
        theirs = {r["description"] for r in as_ana.get("/api/v1/transactions").json()}
        assert "Mercadona vecinos" not in mine
        assert theirs == {"Mercadona vecinos"}
