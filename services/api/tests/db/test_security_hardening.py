"""Correcciones de la revisión de seguridad de OF-101..103."""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from openfinance.infrastructure.config import Settings
from openfinance.infrastructure.db.models import AccountRow, TransactionRow
from openfinance.infrastructure.throttle import LoginThrottle
from openfinance.main import create_app
from tests.db.conftest import PASSWORD, login


class TestLoginThrottle:
    def test_blocks_after_repeated_failures_for_an_email(self, client, seed) -> None:
        for _ in range(5):
            assert login(client, "raul@example.org", "mala-contraseña").status_code == 401
        blocked = login(client, "raul@example.org", PASSWORD)
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        assert login(client, "elena@example.org").status_code == 200

    def test_success_resets_the_email_counter(self, client, seed) -> None:
        for _ in range(4):
            login(client, "raul@example.org", "mala-contraseña")
        assert login(client, "raul@example.org").status_code == 200
        for _ in range(4):
            login(client, "raul@example.org", "mala-contraseña")
        assert login(client, "raul@example.org").status_code == 200

    def test_window_expires(self) -> None:
        t = LoginThrottle(2, 100, timedelta(minutes=15))
        now = datetime(2026, 10, 31, 12, 0)  # noqa: DTZ001
        assert t.try_acquire("a@b.c", "1.2.3.4", now)
        assert t.try_acquire("A@B.C", "1.2.3.4", now)
        assert not t.try_acquire("a@b.c", "1.2.3.4", now)
        assert t.try_acquire("a@b.c", "1.2.3.4", now + timedelta(minutes=16))

    def test_blocks_by_ip_across_emails(self) -> None:
        t = LoginThrottle(100, 3, timedelta(minutes=15))
        now = datetime(2026, 10, 31, 12, 0)  # noqa: DTZ001
        for i in range(3):
            assert t.try_acquire(f"u{i}@b.c", "9.9.9.9", now)
        assert not t.try_acquire("otro@b.c", "9.9.9.9", now)
        assert t.try_acquire("otro@b.c", "8.8.8.8", now)


class TestSessions:
    def test_login_replaces_the_previous_session(self, as_raul) -> None:
        old = as_raul.cookies.get("of_session")
        assert login(as_raul, "raul@example.org").status_code == 200
        new = as_raul.cookies.get("of_session")
        assert new != old
        as_raul.cookies.set("of_session", old)
        assert as_raul.get("/api/v1/me").status_code == 401

    def test_validation_errors_do_not_echo_input(self, client, seed) -> None:
        secret = "x" * 300
        r = client.post(
            "/api/v1/auth/login", json={"email": "raul@example.org", "password": secret}
        )
        assert r.status_code == 422
        assert secret not in r.text
        assert r.json()["detail"][0]["loc"] == ["body", "password"]


class TestProductionDefaults:
    def test_cookie_is_secure_in_production_by_default(self) -> None:
        assert Settings(environment="production").cookie_secure is True
        assert Settings(environment="development").cookie_secure is False
        assert (
            Settings(environment="production", session_cookie_secure=False).cookie_secure is False
        )

    def test_wildcard_cors_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(cors_origins=["*"])

    def test_docs_are_hidden_in_production(self) -> None:
        prod = TestClient(create_app(Settings(environment="production")))
        dev = TestClient(create_app(Settings(environment="development")))
        assert prod.get("/docs").status_code == 404
        assert prod.get("/openapi.json").status_code == 404
        assert dev.get("/openapi.json").status_code == 200


class TestDatabaseIntegrity:
    def test_transaction_cannot_point_to_an_account_of_another_household(
        self, session_factory, seed
    ) -> None:
        with session_factory() as s:
            s.add(
                TransactionRow(
                    id=uuid4(),
                    household_id=seed.joint.household_id,
                    account_id=seed.other_joint.id,
                    booked_at=datetime(2026, 10, 1),  # noqa: DTZ001
                    value_date=date(2026, 10, 1),
                    description="cruzado",
                    amount=-1,
                    currency="EUR",
                    kind="expense",
                    bank_type="",
                    source="manual",
                )
            )
            with pytest.raises(IntegrityError):
                s.flush()

    def test_personal_account_owner_must_belong_to_household(self, session_factory, seed) -> None:
        with session_factory() as s:
            s.add(
                AccountRow(
                    id=uuid4(),
                    household_id=seed.joint.household_id,
                    name="De Ana en nuestra casa",
                    institution="bankinter",
                    kind="personal",
                    currency="EUR",
                    opening_balance=0,
                    owner_id=seed.ana.id,
                )
            )
            with pytest.raises(IntegrityError):
                s.flush()

    def test_contribution_member_must_belong_to_household(self, session_factory, seed) -> None:
        with session_factory() as s:
            s.add(
                TransactionRow(
                    id=uuid4(),
                    household_id=seed.joint.household_id,
                    account_id=seed.joint.id,
                    booked_at=datetime(2026, 10, 1),  # noqa: DTZ001
                    value_date=date(2026, 10, 1),
                    description="aportación de alguien ajeno",
                    amount=10,
                    currency="EUR",
                    kind="contribution",
                    member_id=seed.ana.id,
                    bank_type="",
                    source="manual",
                )
            )
            with pytest.raises(IntegrityError):
                s.flush()
