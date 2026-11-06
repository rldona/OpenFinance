"""OF-105: importación con vista previa y confirmación idempotente."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from openfinance.api.v1 import imports as imports_api
from openfinance.domain.ledger import Account, AccountKind, Institution
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork

FIXTURE = (Path(__file__).parents[1] / "fixtures" / "revolut_joint_synthetic.csv").read_bytes()
NEW_ROW = b"CARD_PAYMENT,Current,2026-10-12 09:00:00,2026-10-12 09:00:01,Panaderia,-3.20,0.00,EUR,COMPLETED,2616.49\n"  # noqa: E501


def upload(client: TestClient, account_id, content: bytes = FIXTURE, name: str = "revolut.csv"):
    return client.post(
        "/api/v1/imports",
        data={"account_id": str(account_id)},
        files={"file": (name, content, "text/csv")},
    )


def commit(client: TestClient, import_id: str):
    return client.post(f"/api/v1/imports/{import_id}/commit")


def joint_count(client: TestClient, seed) -> int:
    rows = client.get("/api/v1/transactions", params={"account_id": str(seed.joint.id)}).json()
    return len(rows)


class TestPreview:
    def test_preview_classifies_and_does_not_save(self, as_raul, seed) -> None:
        before = joint_count(as_raul, seed)
        r = upload(as_raul, seed.joint.id)
        assert r.status_code == 201
        p = r.json()
        assert (p["new_count"], p["duplicate_count"], p["skipped_count"]) == (10, 0, 3)
        kinds = {row["description"]: (row["kind"], row["member_id"]) for row in p["rows"]}
        assert kinds["Payment from Raul Lopez"] == ("contribution", str(seed.raul.id))
        assert kinds["Transfer from ELENA MARTIN"] == ("contribution", str(seed.elena.id))
        assert kinds["To pocket EUR Ahorro"] == ("savings_transfer", None)
        assert kinds["Bizum from Lucia"] == ("income", None)
        assert joint_count(as_raul, seed) == before

    def test_preview_reports_balances(self, as_raul, seed) -> None:
        p = upload(as_raul, seed.joint.id).json()
        assert p["bank_balance"] == {"amount": "2619.69", "currency": "EUR"}
        # 1227.26 de partida + 2519.69 del extracto (2619.69 - 100 previos al primer movimiento)
        assert p["balance_after_import"]["amount"] == "3746.95"
        assert p["balance_mismatches"] == []

    def test_preview_explains_skipped_rows(self, as_raul, seed) -> None:
        reasons = [s["reason"] for s in upload(as_raul, seed.joint.id).json()["skipped"]]
        assert "pendiente: se importará cuando se complete" in reasons

    def test_filename_is_sanitized(self, as_raul, seed) -> None:
        p = upload(as_raul, seed.joint.id, name="../../etc/passwd.csv").json()
        assert p["filename"] == "passwd.csv"


class TestCommit:
    def test_commit_saves_new_rows_with_provenance(self, as_raul, seed) -> None:
        before = joint_count(as_raul, seed)
        p = upload(as_raul, seed.joint.id).json()
        r = commit(as_raul, p["id"])
        assert r.status_code == 200
        assert r.json() == {
            "id": p["id"],
            "status": "committed",
            "created": 10,
            "duplicates": 0,
            "skipped": 3,
        }
        assert joint_count(as_raul, seed) == before + 10
        rows = as_raul.get("/api/v1/transactions", params={"q": "Iberdrola"}).json()
        assert rows[0]["source"] == "import:revolut.csv"

    def test_two_identical_coffees_are_both_saved(self, as_raul, seed) -> None:
        commit(as_raul, upload(as_raul, seed.joint.id).json()["id"])
        cafes = as_raul.get("/api/v1/transactions", params={"q": "Café Central"}).json()
        assert len(cafes) == 2

    def test_committing_twice_does_not_duplicate(self, as_raul, seed) -> None:
        p = upload(as_raul, seed.joint.id).json()
        first = commit(as_raul, p["id"]).json()
        count = joint_count(as_raul, seed)
        again = commit(as_raul, p["id"])
        assert again.status_code == 200
        assert again.json() == first
        assert joint_count(as_raul, seed) == count

    def test_importing_the_same_file_again_creates_nothing(self, as_raul, as_elena, seed) -> None:
        commit(as_raul, upload(as_raul, seed.joint.id).json()["id"])
        count = joint_count(as_raul, seed)
        p = upload(as_elena, seed.joint.id).json()
        assert (p["new_count"], p["duplicate_count"]) == (0, 10)
        assert all(row["duplicate"] for row in p["rows"])
        assert commit(as_elena, p["id"]).json()["created"] == 0
        assert joint_count(as_raul, seed) == count

    def test_overlapping_statement_only_adds_new_rows(self, as_raul, seed) -> None:
        commit(as_raul, upload(as_raul, seed.joint.id).json()["id"])
        p = upload(as_raul, seed.joint.id, FIXTURE + NEW_ROW).json()
        assert (p["new_count"], p["duplicate_count"]) == (1, 10)
        assert commit(as_raul, p["id"]).json()["created"] == 1

    def test_file_content_is_deleted_after_commit(self, as_raul, seed, session_factory) -> None:
        p = upload(as_raul, seed.joint.id).json()
        commit(as_raul, p["id"])
        with session_factory() as s:
            from uuid import UUID

            assert SqlUnitOfWork(s).imports.content(UUID(p["id"])) is None

    def test_expired_preview_cannot_be_committed(self, as_raul, seed, monkeypatch) -> None:
        p = upload(as_raul, seed.joint.id).json()
        later = datetime.now(UTC) + timedelta(hours=25)
        monkeypatch.setattr(imports_api, "utc_now", lambda: later)
        r = commit(as_raul, p["id"])
        assert r.status_code == 409
        assert "caducado" in r.json()["detail"]


class TestValidation:
    def test_unsupported_institution(self, as_raul, seed, session_factory) -> None:
        other = Account(
            id=AccountId(uuid4()),
            household_id=seed.joint.household_id,
            name="Otro banco",
            institution=Institution.OTHER,
            kind=AccountKind.JOINT,
            currency=Currency("EUR"),
            opening_balance=Money.of("0", "EUR"),
        )
        with session_factory() as s:
            SqlUnitOfWork(s).accounts.add(other)
            s.commit()
        r = upload(as_raul, other.id)
        assert r.status_code == 422
        assert "other" in r.json()["detail"]

    def test_csv_into_bankinter_is_rejected(self, as_raul, seed) -> None:
        r = upload(as_raul, seed.raul_personal.id)
        assert r.status_code == 422
        assert "Excel" in r.json()["detail"]

    def test_wrong_format(self, as_raul, seed) -> None:
        r = upload(as_raul, seed.joint.id, b"Fecha;Concepto;Importe\n01/10/2026;x;-1,00\n")
        assert r.status_code == 422
        assert "faltan las columnas" in r.json()["detail"]

    def test_empty_and_too_big_files(self, as_raul, seed) -> None:
        assert upload(as_raul, seed.joint.id, b"").status_code == 422
        big = upload(as_raul, seed.joint.id, b"x" * (5 * 1024 * 1024 + 1))
        assert big.status_code == 422  # supera 5 MB pero cabe en el margen del multipart
        huge = upload(as_raul, seed.joint.id, b"x" * (6 * 1024 * 1024))
        assert huge.status_code == 413
        assert "demasiado grande" in huge.json()["detail"]

    def test_writes_require_csrf_header(self, app, seed) -> None:
        plain = TestClient(app)
        r = plain.post(
            "/api/v1/auth/login", json={"email": "raul@example.org", "password": "x" * 12}
        )
        assert r.status_code == 403


class TestIsolation:
    def test_cannot_import_into_partner_personal_account(self, as_raul, seed) -> None:
        assert upload(as_raul, seed.elena_personal.id).status_code == 404

    def test_cannot_import_into_other_household(self, as_raul, seed) -> None:
        assert upload(as_raul, seed.other_joint.id).status_code == 404

    def test_other_household_cannot_see_or_commit_preview(self, as_raul, as_ana, seed) -> None:
        p = upload(as_raul, seed.joint.id).json()
        assert commit(as_ana, p["id"]).status_code == 404
        assert joint_count(as_raul, seed) == 5


class TestReviewFixes:
    def test_losing_a_commit_race_returns_the_winner_result(
        self, as_raul, seed, session_factory
    ) -> None:
        from uuid import UUID

        p = upload(as_raul, seed.joint.id).json()
        before = joint_count(as_raul, seed)
        # Otra petición ha reclamado el lote y ya lo está guardando.
        with session_factory() as s:
            assert SqlUnitOfWork(s).imports.claim(UUID(p["id"])) is True
            assert SqlUnitOfWork(s).imports.claim(UUID(p["id"])) is False
            s.commit()
        r = commit(as_raul, p["id"])
        assert r.status_code == 200
        assert r.json()["status"] == "committed"
        assert joint_count(as_raul, seed) == before

    def test_integrity_conflict_is_a_409_not_a_500(self, as_raul, seed, monkeypatch) -> None:
        from openfinance.infrastructure.db.repositories import SqlTransactionRepository

        commit(as_raul, upload(as_raul, seed.joint.id).json()["id"])
        p = upload(as_raul, seed.joint.id).json()
        # Simula que otra importación guarda las mismas filas entre la comprobación y el insert.
        monkeypatch.setattr(SqlTransactionRepository, "existing_fingerprints", lambda *a: set())
        r = commit(as_raul, p["id"])
        assert r.status_code == 409
        assert "vuelve a intentarlo" in r.json()["detail"]

    def test_malformed_csv_is_a_422_not_a_500(self, as_raul, seed) -> None:
        header = FIXTURE.splitlines()[0]
        huge_field = (
            header
            + b'\nCARD_PAYMENT,Current,2026-10-01 10:00:00,,"'
            + b"x" * 140_000
            + b'",-1,0,EUR,COMPLETED,1\n'
        )
        r = upload(as_raul, seed.joint.id, huge_field)
        assert r.status_code == 422
        assert "CSV mal formado" in r.json()["detail"]

    def test_absurd_amount_is_a_skipped_row_not_a_500(self, as_raul, seed) -> None:
        header = FIXTURE.splitlines()[0]
        row = b"\nCARD_PAYMENT,Current,2026-10-01 10:00:00,,Tienda,1E+50,0,EUR,COMPLETED,1\n"
        r = upload(as_raul, seed.joint.id, header + row)
        assert r.status_code == 201
        assert [s["reason"] for s in r.json()["skipped"]] == ["fila no válida: importe no válido"]

    def test_long_values_fit_their_columns(self, as_raul, seed) -> None:
        header = FIXTURE.splitlines()[0]
        row = (
            b"\nCARD_PAYMENT,Current,2026-10-01 10:00:00,2026-10-01 10:00:01,"
            + b"D" * 600
            + b",-1.00,0,EUR,COMPLETED,99.00\n"
        )
        p = upload(as_raul, seed.joint.id, header + row, name="n" * 300 + ".csv").json()
        assert len(p["rows"][0]["description"]) == 500
        assert commit(as_raul, p["id"]).json()["created"] == 1
        tx = as_raul.get("/api/v1/transactions", params={"q": "DDDD"}).json()[0]
        assert len(tx["source"]) <= 200

    def test_expired_preview_content_is_purged(
        self, as_raul, seed, session_factory, monkeypatch
    ) -> None:
        from uuid import UUID

        old = upload(as_raul, seed.joint.id).json()
        later = datetime.now(UTC) + timedelta(hours=25)
        monkeypatch.setattr(imports_api, "utc_now", lambda: later)
        upload(as_raul, seed.joint.id)
        with session_factory() as s:
            assert SqlUnitOfWork(s).imports.content(UUID(old["id"])) is None

    def test_csrf_403_carries_cors_headers(self, app, seed) -> None:
        plain = TestClient(app)
        r = plain.post("/api/v1/auth/logout", headers={"Origin": "http://localhost:5173"})
        assert r.status_code == 403
        assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


class TestZeroAmounts:
    """OF-601: una fila de importe 0 no puede impedir confirmar el extracto."""

    ZERO = b"CARD_PAYMENT,Current,2026-10-12 09:00:00,2026-10-12 09:00:01,Verificacion tarjeta,0.00,0.00,EUR,COMPLETED,2619.69\n"  # noqa: E501
    EMPTY = b"CARD_PAYMENT,Current,2026-10-12 10:00:00,2026-10-12 10:00:01,Sin importe,,0.00,EUR,COMPLETED,2619.69\n"  # noqa: E501

    def test_zero_amount_row_is_skipped_and_the_statement_commits(self, as_raul, seed) -> None:
        before = joint_count(as_raul, seed)
        r = upload(as_raul, seed.joint.id, FIXTURE + self.ZERO)
        assert r.status_code == 201
        p = r.json()
        assert p["new_count"] == 10
        assert p["balance_mismatches"] == []
        skipped = {s["description"]: s["reason"] for s in p["skipped"]}
        assert skipped["Verificacion tarjeta"] == "importe cero: no mueve dinero"
        c = commit(as_raul, p["id"])
        assert c.status_code == 200
        assert c.json()["created"] == 10
        assert joint_count(as_raul, seed) == before + 10

    def test_missing_amount_is_a_skipped_row(self, as_raul, seed) -> None:
        p = upload(as_raul, seed.joint.id, FIXTURE + self.EMPTY).json()
        skipped = {s["description"]: s["reason"] for s in p["skipped"]}
        assert skipped["Sin importe"] == "fila no válida: falta el importe"
        assert commit(as_raul, p["id"]).status_code == 200

    def test_domain_error_at_commit_is_a_422_and_saves_nothing(
        self, as_raul, seed, monkeypatch
    ) -> None:
        from openfinance.application import imports as imports_app
        from openfinance.domain.ledger import LedgerError

        def reject(**_: object) -> None:
            raise LedgerError("Un movimiento no puede ser de importe cero")

        p = upload(as_raul, seed.joint.id).json()
        before = joint_count(as_raul, seed)
        with monkeypatch.context() as m:
            m.setattr(imports_app, "Transaction", reject)
            r = commit(as_raul, p["id"])
        assert r.status_code == 422
        assert "no se puede guardar" in r.json()["detail"]
        assert joint_count(as_raul, seed) == before
        # El lote no queda reclamado a medias: se puede confirmar después.
        again = commit(as_raul, p["id"])
        assert again.status_code == 200
        assert again.json()["created"] == 10
