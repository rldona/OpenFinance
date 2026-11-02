"""OF-501: exportación del hogar. Exporta lo que ve quien la pide (ADR-0013)."""

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from openfinance import cli
from openfinance.api.export_formats import CSV_FILES, MANIFEST, render_csv_zip, safe_cell
from openfinance.api.v1 import export as export_api
from openfinance.application.export import EXPORT_FORMAT_VERSION, export_household
from openfinance.application.identity import revoke_all_sessions
from openfinance.domain.categories import CategoryRule
from openfinance.domain.imports import MemberPattern, PatternDirection
from openfinance.domain.insights import Month
from openfinance.domain.ledger import (
    Account,
    AccountKind,
    Institution,
    Transaction,
    TransactionKind,
)
from openfinance.domain.savings import Budget, Goal, GoalId
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.domain.workspaces import Actor
from openfinance.infrastructure.db.repositories import SqlUnitOfWork

NOW = datetime(2026, 11, 1, tzinfo=UTC)
FORMULA = '=HYPERLINK("http://example.org","x")'
SEMICOLON_FORMULA = 'COMPRA;=HYPERLINK("http://example.org","y")'
ELENA_SECRET_RULE = "PELUQUERIA ELENA"
ELENA_OUTFLOW = "ELENA A CASA"


@pytest.fixture
def data(session_factory, seed):
    """Añade al seed una hucha, reglas, patrones, presupuestos y objetivos de ambos."""
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        house = seed.joint.household_id
        other_house = seed.other_joint.household_id
        hucha = Account(
            id=AccountId(uuid4()),
            household_id=house,
            name="Hucha vacaciones",
            institution=Institution.REVOLUT,
            kind=AccountKind.SAVINGS,
            currency=Currency("EUR"),
            opening_balance=Money.of("250.00", "EUR"),
        )
        uow.accounts.add(hucha)
        uow.transactions.add(
            Transaction(
                id=TransactionId(uuid4()),
                household_id=house,
                account_id=seed.joint.id,
                booked_at=datetime(2026, 10, 10, 12),  # noqa: DTZ001
                value_date=datetime(2026, 10, 10).date(),  # noqa: DTZ001
                description=FORMULA,
                amount=Money.of("-12.30", "EUR"),
                kind=TransactionKind.EXPENSE,
                fingerprint="huella-secreta",
            )
        )
        uow.transactions.add(
            Transaction(
                id=TransactionId(uuid4()),
                household_id=house,
                account_id=seed.joint.id,
                booked_at=datetime(2026, 10, 11, 12),  # noqa: DTZ001
                value_date=datetime(2026, 10, 11).date(),  # noqa: DTZ001
                description=SEMICOLON_FORMULA,
                amount=Money.of("-1.00", "EUR"),
                kind=TransactionKind.EXPENSE,
            )
        )
        cats = {c.slug: c.id for c in uow.categories.for_household(house)}
        uow.rules.upsert(CategoryRule(house, "MERCADONA", cats["super"]), NOW)
        uow.rules.upsert(
            CategoryRule(house, "AMAZON MARKET", cats["hogar"], str(seed.raul.id)), NOW
        )
        uow.rules.upsert(
            CategoryRule(house, ELENA_SECRET_RULE, cats["salud"], str(seed.elena.id)), NOW
        )
        other_cats = uow.categories.for_household(other_house)
        uow.rules.upsert(CategoryRule(other_house, "VECINOS SA", other_cats[0].id), NOW)
        for p in (
            MemberPattern(house, seed.raul.id, "*1234"),
            MemberPattern(house, seed.raul.id, "RAUL A CASA", PatternDirection.OUTFLOW),
            MemberPattern(house, seed.elena.id, "*5678"),
            MemberPattern(house, seed.elena.id, ELENA_OUTFLOW, PatternDirection.OUTFLOW),
        ):
            uow.member_patterns.add(p, NOW)

        def goal(name: str, account: AccountId | None, household=house) -> Goal:
            return Goal(
                id=GoalId(uuid4()),
                household_id=household,
                name=name,
                icon="🎯",
                target=Money.of("3000", "EUR"),
                monthly=Money.of("150", "EUR"),
                saved=Money.of("40.5", "EUR"),
                deadline=Month(2027, 6),
                account_id=account,
            )

        uow.budgets.upsert(Budget(house, cats["super"], Money.of("400", "EUR")))
        uow.goals.add(goal("Viaje", hucha.id))
        # Datos antiguos: un objetivo vinculado a una cuenta que Raúl no ve.
        uow.goals.add(goal("Algo de Elena", seed.elena_personal.id))
        uow.goals.add(goal("Coche vecinos", None, other_house))
        uow.commit()
    return hucha


def zip_files(content: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return {n: archive.read(n).decode("utf-8-sig") for n in archive.namelist()}


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


FORBIDDEN_WORDS = ("fingerprint", "huella-secreta", "token", "password", "fake$", "import_id")


def assert_private_data_absent(blob: str, seed) -> None:
    for secret in (
        str(seed.elena_personal.id),
        seed.elena_personal.name,
        "Peluquería",
        ELENA_SECRET_RULE,
        ELENA_OUTFLOW,
        str(seed.other_joint.id),
        seed.other_joint.name,
        "Mercadona vecinos",
        "VECINOS SA",
        "Coche vecinos",
        "Vecinos",
        str(seed.ana.id),
        "elena@example.org",
        *FORBIDDEN_WORDS,
    ):
        assert secret not in blob, secret


class TestJson:
    def test_contains_what_raul_sees_and_nothing_else(self, as_raul, seed, data) -> None:
        r = as_raul.get("/api/v1/export")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        blob = r.content.decode("utf-8")
        assert_private_data_absent(blob, seed)

        body = json.loads(blob)
        assert body["format_version"] == EXPORT_FORMAT_VERSION == 1
        assert body["meta"]["exported_by_email"] == "raul@example.org"
        assert body["meta"]["household_name"] == "Nuestra casa"
        assert {a["name"] for a in body["accounts"]} == {
            "Cuenta conjunta",
            "Bankinter Raúl",
            "Hucha vacaciones",
        }
        assert {m["display_name"] for m in body["members"]} == {"Raúl", "Elena"}
        assert all(set(m) == {"id", "display_name"} for m in body["members"])
        assert {(r["merchant"], r["scope"]) for r in body["rules"]} == {
            ("MERCADONA", "household"),
            ("AMAZON MARKET", "personal"),
        }
        assert {(p["pattern"], p["direction"]) for p in body["member_patterns"]} == {
            ("*1234", "inflow"),
            ("RAUL A CASA", "outflow"),
            ("*5678", "inflow"),
        }
        assert body["budgets"] == [
            {
                "category_id": body["budgets"][0]["category_id"],
                "amount": "400.00",
                "currency": "EUR",
            }
        ]
        goals = {g["name"]: g for g in body["goals"]}
        assert set(goals) == {"Viaje", "Algo de Elena"}
        assert goals["Viaje"]["account_id"] == str(data.id)
        assert goals["Algo de Elena"]["account_id"] is None
        assert goals["Viaje"]["saved"] == "250.00"  # saldo de la hucha, como en la app
        assert goals["Algo de Elena"]["saved"] == "40.50"  # cuenta no visible: lo anotado
        assert goals["Viaje"]["deadline"] == "2027-06"

    def test_amounts_are_exact_text_and_dates_iso(self, as_raul, seed, data) -> None:
        body = as_raul.get("/api/v1/export", params={"format": "json"}).json()
        accounts = {a["name"]: a for a in body["accounts"]}
        assert accounts["Cuenta conjunta"]["opening_balance"] == "100.00"
        # 100 + 1600 - 300 - 87.34 - 25.40 - 60 - 12.30 - 1.00
        assert accounts["Cuenta conjunta"]["balance"] == "1213.96"
        assert accounts["Hucha vacaciones"]["balance"] == "250.00"
        formula = next(t for t in body["transactions"] if t["amount"] == "-12.30")
        assert formula["description"] == FORMULA
        assert formula["booked_at"] == "2026-10-10T12:00:00"
        assert formula["value_date"] == "2026-10-10"
        assert set(formula) >= {"merchant", "kind", "source", "bank_type", "category"}
        booked = [t["booked_at"] for t in body["transactions"]]
        assert booked == sorted(booked)

    def test_elena_does_not_see_raul_personal(self, as_elena, seed, data) -> None:
        body = as_elena.get("/api/v1/export").json()
        names = {a["name"] for a in body["accounts"]}
        assert "Bankinter Elena" in names
        assert "Bankinter Raúl" not in names
        assert "Aportación casa" not in json.dumps(body, ensure_ascii=False)
        assert ("RAUL A CASA", "outflow") not in {
            (p["pattern"], p["direction"]) for p in body["member_patterns"]
        }
        assert "AMAZON MARKET" not in {r["merchant"] for r in body["rules"]}

    def test_other_household_exports_only_its_own(self, as_ana, seed, data) -> None:
        blob = as_ana.get("/api/v1/export").text
        assert "Nuestra casa" not in blob
        assert "Cuenta conjunta" not in blob
        assert str(seed.joint.id) not in blob
        assert "Coche vecinos" in blob


class TestCsvZip:
    def test_one_csv_per_entity_without_private_data(self, as_raul, seed, data) -> None:
        r = as_raul.get("/api/v1/export", params={"format": "csv"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        files = zip_files(r.content)
        assert set(files) == {MANIFEST, *(f"{n}.csv" for n in CSV_FILES)}
        for text in files.values():
            assert_private_data_absent(text, seed)

        assert json.loads(files[MANIFEST])["format_version"] == 1
        accounts = {a["name"] for a in rows(files["accounts.csv"])}
        assert accounts == {"Cuenta conjunta", "Bankinter Raúl", "Hucha vacaciones"}
        txns = rows(files["transactions.csv"])
        formula = next(t for t in txns if t["amount"] == "-12.30")
        assert formula["description"] == "'" + FORMULA
        assert {t["amount"] for t in txns} >= {"-87.34", "1600.00", "-1600.00"}
        goals = {g["name"]: g for g in rows(files["goals.csv"])}
        assert goals["Algo de Elena"]["account_id"] == ""

    def test_csv_is_utf8_with_bom_and_crlf(self, as_raul, seed, data) -> None:
        r = as_raul.get("/api/v1/export", params={"format": "csv"})
        with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
            raw = archive.read("accounts.csv")
            assert archive.testzip() is None
        assert raw.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" in raw
        assert "Bankinter Raúl" in raw.decode("utf-8-sig")
        # Todos los campos entre comillas, también los importes.
        header, first = raw.decode("utf-8-sig").splitlines()[:2]
        assert header.startswith('"id","name",')
        columns = header.count(",") + 1
        assert first.startswith('"') and first.endswith('"')
        assert first.count('","') == columns - 1

    def test_formula_after_semicolon_is_neutralized(self, as_raul, seed, data) -> None:
        files = zip_files(as_raul.get("/api/v1/export", params={"format": "csv"}).content)
        txns = rows(files["transactions.csv"])
        semicolon = next(t for t in txns if t["amount"] == "-1.00")
        assert semicolon["description"] == "'" + SEMICOLON_FORMULA
        json_body = as_raul.get("/api/v1/export").json()
        assert SEMICOLON_FORMULA in {t["description"] for t in json_body["transactions"]}


class TestHttp:
    def test_requires_session(self, client, seed) -> None:
        assert client.get("/api/v1/export").status_code == 401

    def test_invalid_format_is_422(self, as_raul) -> None:
        assert as_raul.get("/api/v1/export", params={"format": "xlsx"}).status_code == 422

    def test_download_headers(self, as_raul, monkeypatch) -> None:
        monkeypatch.setattr(export_api, "local_today", lambda: datetime(2026, 11, 1).date())  # noqa: DTZ001
        for fmt, ext in (("json", "json"), ("csv", "zip")):
            r = as_raul.get("/api/v1/export", params={"format": fmt})
            assert r.headers["content-disposition"] == (
                f'attachment; filename="openfinance-2026-11-01.{ext}"'
            )
            assert r.headers["cache-control"] == "no-store"
            assert r.headers["x-content-type-options"] == "nosniff"

    def test_get_does_not_need_csrf_header(self, app, as_raul) -> None:
        bare = TestClient(app)
        bare.cookies.update(as_raul.cookies)
        assert bare.get("/api/v1/export").status_code == 200


class TestUnit:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("=1+1", "'=1+1"),
            ("+34 600", "'+34 600"),
            ("-resta", "'-resta"),
            ("@SUM(A1)", "'@SUM(A1)"),
            ("\tTAB", "'\tTAB"),
            ("\rCR", "'\rCR"),
            ("Mercadona", "Mercadona"),
            ("", ""),
            ("a=b", "a=b"),
            ('COMPRA;=HYPERLINK("http://x")', '\'COMPRA;=HYPERLINK("http://x")'),
            ("COMPRA; @SUM(A1)", "'COMPRA; @SUM(A1)"),
            ("LINEA\n-1", "'LINEA\n-1"),
            ("  =1", "'  =1"),
            ("PAGO 50% dto", "PAGO 50% dto"),
            ("A-B", "A-B"),
        ],
    )
    def test_safe_cell(self, value: str, expected: str) -> None:
        assert safe_cell(value) == expected

    def test_zip_names_and_negative_amounts_untouched(self, session_factory, seed, data) -> None:
        with session_factory() as s:
            export = export_household(
                SqlUnitOfWork(s), Actor(seed.raul.id, seed.joint.household_id), NOW, "test"
            )
        assert all(isinstance(t.amount, Decimal) for t in export.transactions)
        files = zip_files(render_csv_zip(export))
        assert sorted(files) == sorted(
            [
                "manifest.json",
                "members.csv",
                "accounts.csv",
                "transactions.csv",
                "categories.csv",
                "rules.csv",
                "budgets.csv",
                "goals.csv",
                "member_patterns.csv",
                "exchange_rates.csv",
            ]
        )
        amounts = [t["amount"] for t in rows(files["transactions.csv"])]
        assert "-87.34" in amounts
        assert not any(a.startswith("'") for a in amounts)
        header = files["transactions.csv"].splitlines()[0].split(",")
        assert "fingerprint" not in header
        assert "import_id" not in header


class TestRevokeSessions:
    def test_previous_cookie_stops_working(self, as_raul, session_factory) -> None:
        assert as_raul.get("/api/v1/me").status_code == 200
        with session_factory() as s:
            assert revoke_all_sessions(SqlUnitOfWork(s), NOW) == 1
        assert as_raul.get("/api/v1/me").status_code == 401

    def test_cli_prints_the_number(
        self, as_raul, as_elena, session_factory, monkeypatch, capsys
    ) -> None:
        monkeypatch.setattr(cli, "get_session_factory", lambda: session_factory)
        assert cli.main(["sessions", "revoke-all"]) == 0
        assert capsys.readouterr().out.strip() == "2"
        assert as_raul.get("/api/v1/me").status_code == 401
        assert as_elena.get("/api/v1/me").status_code == 401
        assert cli.main(["sessions", "revoke-all"]) == 0
        assert capsys.readouterr().out.strip() == "0"
