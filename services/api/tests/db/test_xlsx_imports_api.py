"""OF-104 y OF-107: importar extractos en Excel (Revolut conjunta y Bankinter personal).

Datos sintéticos: ni conceptos ni cuentas reales.
"""

from datetime import UTC, date, datetime

import pytest

from openfinance.api.v1 import insights as insights_api
from openfinance.domain.imports import MemberPattern, PatternDirection
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from tests.xlsx_factory import make_xlsx

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NOW = datetime(2026, 11, 1, tzinfo=UTC)

BANKINTER_HEADER = ["Fecha contable", "Fecha valor", "Descripción", "Importe", "Saldo", "Divisa"]
BANKINTER_ROWS = [
    ["05/10/2026", "05/10/2026", "NOMINA EMPRESA FICTICIA", 2000, 2900, "EUR"],
    ["06/10/2026", "06/10/2026", "Revolut**1234*", -800, 2100, "EUR"],
    ["07/10/2026", "07/10/2026", "BIZUM DE ELENA", 30, 2130, "EUR"],
    ["08/10/2026", "08/10/2026", "TRANSF A ELENA", -50, 2080, "EUR"],
]
REVOLUT_HEADER = [
    "Tipo",
    "Producto",
    "Fecha de inicio",
    "Fecha de finalizaciÃ³n",
    "DescripciÃ³n",
    "Importe",
    "ComisiÃ³n",
    "Divisa",
    "State",
    "Saldo",
]


def bankinter_xlsx() -> bytes:
    rows = [
        ["MOVIMIENTOS DE LA CUENTA ES9100000000000000000000"],
        [],
        ["MOVIMIENTOS"],
        BANKINTER_HEADER,
        *reversed(BANKINTER_ROWS),
    ]
    return make_xlsx(rows, sheet="Movimientos")


def revolut_xlsx() -> bytes:
    def at(day: int) -> datetime:
        return datetime(2026, 10, day, 12)  # noqa: DTZ001 - hora local del extracto

    rows = [
        ["Transferir", "Actual", at(12), at(12), "Transferencia de Elena Martín", 500.0, 0.0, "EUR", "COMPLETADO", 600.0],  # noqa: E501
        ["Recargas", "Actual", at(13), at(13), "Recarga de *1234", 300.0, 0.0, "EUR", "COMPLETADO", 900.0],  # noqa: E501
        ["Recargas", "Actual", at(14), at(14), "Recarga de *9999", 100.0, 0.0, "EUR", "COMPLETADO", 1000.0],  # noqa: E501
        ["Pago con tarjeta", "Actual", at(15), at(15), "Revolut**1234* tienda", -20.0, 0.0, "EUR", "COMPLETADO", 980.0],  # noqa: E501
    ]  # fmt: skip
    return make_xlsx([REVOLUT_HEADER, *rows])


def upload(client, account_id, content: bytes, name: str = "extracto.xlsx"):
    return client.post(
        "/api/v1/imports",
        data={"account_id": str(account_id)},
        files={"file": (name, content, XLSX)},
    )


def kinds(preview: dict) -> dict[str, tuple[str, str | None]]:
    return {r["description"]: (r["kind"], r["member_id"]) for r in preview["rows"]}


@pytest.fixture
def patterns(session_factory, seed) -> None:
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        house = uow.households.households_of(seed.raul.id)[0]
        other = uow.households.households_of(seed.ana.id)[0]
        uow.member_patterns.add(MemberPattern(house, seed.raul.id, "*1234"), NOW)
        uow.member_patterns.add(
            MemberPattern(house, seed.elena.id, "BIZUM DE ELENA", PatternDirection.OUTFLOW), NOW
        )
        uow.member_patterns.add(MemberPattern(other, seed.ana.id, "*9999"), NOW)
        uow.commit()


class TestBankinterPersonal:
    def test_preview_classifies_with_owner_rules(self, as_raul, seed, patterns) -> None:
        r = upload(as_raul, seed.raul_personal.id, bankinter_xlsx())
        assert r.status_code == 201
        p = r.json()
        assert kinds(p) == {
            "NOMINA EMPRESA FICTICIA": ("income", None),
            "Revolut**1234*": ("contribution", str(seed.raul.id)),
            # En una cuenta personal, el nombre de la pareja no es una aportación.
            "BIZUM DE ELENA": ("income", None),
            "TRANSF A ELENA": ("expense", None),
        }
        assert p["bank_balance"] == {"amount": "2080.00", "currency": "EUR"}
        assert p["balance_mismatches"] == []
        assert [r["booked_at"][:10] for r in p["rows"]] == [
            "2026-10-05",
            "2026-10-06",
            "2026-10-07",
            "2026-10-08",
        ]

    def test_contribution_from_personal_does_not_change_household_totals(
        self, as_raul, seed, monkeypatch
    ) -> None:
        monkeypatch.setattr(insights_api, "local_today", lambda: date(2026, 11, 15))

        def month():
            return as_raul.get("/api/v1/insights/month", params={"month": "2026-10"}).json()

        before = month()
        p = upload(as_raul, seed.raul_personal.id, bankinter_xlsx()).json()
        assert as_raul.post(f"/api/v1/imports/{p['id']}/commit").json()["created"] == 4
        after = month()
        for key in ("spent", "inflow", "saved", "contributions", "categories"):
            assert after[key] == before[key]
        rows = as_raul.get(
            "/api/v1/transactions", params={"account_id": str(seed.raul_personal.id)}
        ).json()
        revolut = next(t for t in rows if t["description"] == "Revolut**1234*")
        assert (revolut["kind"], revolut["member_id"]) == ("contribution", str(seed.raul.id))

    def test_reimporting_creates_nothing(self, as_raul, seed) -> None:
        p = upload(as_raul, seed.raul_personal.id, bankinter_xlsx()).json()
        as_raul.post(f"/api/v1/imports/{p['id']}/commit")
        again = upload(as_raul, seed.raul_personal.id, bankinter_xlsx()).json()
        assert (again["new_count"], again["duplicate_count"]) == (0, 4)


class TestBankinterIsolation:
    def test_partner_cannot_preview_into_it(self, as_elena, seed) -> None:
        assert upload(as_elena, seed.raul_personal.id, bankinter_xlsx()).status_code == 404

    def test_partner_cannot_commit_the_owner_preview(self, as_raul, as_elena, seed) -> None:
        p = upload(as_raul, seed.raul_personal.id, bankinter_xlsx()).json()
        assert as_elena.post(f"/api/v1/imports/{p['id']}/commit").status_code == 404

    def test_partner_cannot_see_imported_movements(self, as_raul, as_elena, seed) -> None:
        p = upload(as_raul, seed.raul_personal.id, bankinter_xlsx()).json()
        as_raul.post(f"/api/v1/imports/{p['id']}/commit")
        r = as_elena.get("/api/v1/transactions", params={"account_id": str(seed.raul_personal.id)})
        assert r.status_code == 404
        texts = [t["description"] for t in as_elena.get("/api/v1/transactions").json()]
        assert "Revolut**1234*" not in texts
        assert "NOMINA EMPRESA FICTICIA" not in texts

    def test_other_household_cannot_commit(self, as_raul, as_ana, seed) -> None:
        p = upload(as_raul, seed.raul_personal.id, bankinter_xlsx()).json()
        assert as_ana.post(f"/api/v1/imports/{p['id']}/commit").status_code == 404
        assert upload(as_ana, seed.raul_personal.id, bankinter_xlsx()).status_code == 404


class TestRevolutJointXlsx:
    def test_names_and_inflow_patterns_identify_contributions(
        self, as_raul, seed, patterns
    ) -> None:
        r = upload(as_raul, seed.joint.id, revolut_xlsx())
        assert r.status_code == 201
        p = r.json()
        assert kinds(p) == {
            "Transferencia de Elena Martín": ("contribution", str(seed.elena.id)),
            "Recarga de *1234": ("contribution", str(seed.raul.id)),
            # El patrón es de otro hogar: aquí no cuenta.
            "Recarga de *9999": ("income", None),
            # Los patrones de salida son solo para cuentas personales.
            "Revolut**1234* tienda": ("expense", None),
        }
        assert p["bank_balance"] == {"amount": "980.00", "currency": "EUR"}
        assert p["balance_mismatches"] == []
        assert p["filename"] == "extracto.xlsx"

    def test_commit(self, as_raul, seed, patterns) -> None:
        p = upload(as_raul, seed.joint.id, revolut_xlsx()).json()
        assert as_raul.post(f"/api/v1/imports/{p['id']}/commit").json()["created"] == 4

    def test_corrupt_excel_is_a_422(self, as_raul, seed) -> None:
        r = upload(as_raul, seed.joint.id, revolut_xlsx()[:300])
        assert r.status_code == 422
        assert "Excel" in r.json()["detail"]
