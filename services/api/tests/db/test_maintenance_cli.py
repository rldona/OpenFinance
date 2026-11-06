"""Mantenimiento desde el servidor: contraseñas y cuentas (OF-606)."""

import pytest
from fastapi.testclient import TestClient

from openfinance import cli
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.households import NewAccount, add_account
from openfinance.application.identity import set_password
from openfinance.domain.ledger import AccountKind, Institution
from openfinance.infrastructure.db.repositories import SqlUnitOfWork

from .conftest import CSRF, PASSWORD, FakeHasher, login

NEW_PASSWORD = "otra-clave-muy-larga"


class TestSetPassword:
    def test_old_session_is_401_and_the_new_password_works(
        self, app, session_factory, seed, as_raul, as_elena
    ) -> None:
        with session_factory() as s:
            revoked = set_password(SqlUnitOfWork(s), FakeHasher(), "Raul@Example.org", NEW_PASSWORD)
        assert revoked == 1
        assert as_raul.get("/api/v1/me").status_code == 401
        # Solo se cierran las sesiones de esa persona.
        assert as_elena.get("/api/v1/me").status_code == 200
        fresh = TestClient(app, headers=CSRF)
        assert login(fresh, "raul@example.org").status_code == 401
        assert login(fresh, "raul@example.org", NEW_PASSWORD).status_code == 200

    def test_weak_password_and_unknown_email(self, session_factory, seed) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            with pytest.raises(InvalidRequestError, match="al menos"):
                set_password(uow, FakeHasher(), "raul@example.org", "corta")
            with pytest.raises(NotFoundError):
                set_password(uow, FakeHasher(), "nadie@example.org", NEW_PASSWORD)


class TestAddAccount:
    def test_adds_a_pocket_visible_to_the_household(self, session_factory, seed, as_elena) -> None:
        pocket = NewAccount("Hucha viaje", Institution.REVOLUT, AccountKind.SAVINGS, "120.50")
        with session_factory() as s:
            add_account(SqlUnitOfWork(s), "raul@example.org", pocket)
        names = {a["name"] for a in as_elena.get("/api/v1/accounts").json()}
        assert "Hucha viaje" in names

    def test_personal_account_is_private_to_its_owner(
        self, session_factory, seed, as_raul, as_elena
    ) -> None:
        spec = NewAccount(
            "Revolut Raúl",
            Institution.REVOLUT,
            AccountKind.PERSONAL,
            owner_email="raul@example.org",
        )
        with session_factory() as s:
            add_account(SqlUnitOfWork(s), "raul@example.org", spec)
        assert "Revolut Raúl" in {a["name"] for a in as_raul.get("/api/v1/accounts").json()}
        assert "Revolut Raúl" not in {a["name"] for a in as_elena.get("/api/v1/accounts").json()}

    def test_owner_must_belong_to_the_household(self, session_factory, seed) -> None:
        spec = NewAccount(
            "De Ana", Institution.BANKINTER, AccountKind.PERSONAL, owner_email="ana@example.org"
        )
        with session_factory() as s, pytest.raises(InvalidRequestError, match="no es del hogar"):
            add_account(SqlUnitOfWork(s), "raul@example.org", spec)

    def test_repeated_name_is_a_conflict(self, session_factory, seed) -> None:
        spec = NewAccount("cuenta CONJUNTA", Institution.REVOLUT, AccountKind.JOINT)
        with session_factory() as s, pytest.raises(ConflictError):
            add_account(SqlUnitOfWork(s), "raul@example.org", spec)


class TestCli:
    @pytest.fixture(autouse=True)
    def database(self, monkeypatch, session_factory):
        monkeypatch.setattr(cli, "get_session_factory", lambda: session_factory)
        monkeypatch.setattr(cli, "Argon2PasswordHasher", FakeHasher)

    def test_set_password_asks_without_echo(self, monkeypatch, seed, as_raul, capsys) -> None:
        answers = iter([NEW_PASSWORD, NEW_PASSWORD])
        monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(answers))
        assert cli.main(["users", "set-password", "raul@example.org"]) == 0
        out = capsys.readouterr().out
        assert "1 sesión cerrada" in out
        assert NEW_PASSWORD not in out
        assert as_raul.get("/api/v1/me").status_code == 401

    def test_accounts_add(self, seed, as_elena, capsys) -> None:
        args = ["accounts", "add", "elena@example.org", "Hucha casa", "--kind", "savings"]
        assert cli.main(args) == 0
        assert "Hucha casa" in {a["name"] for a in as_elena.get("/api/v1/accounts").json()}
        args = ["accounts", "add", "elena@example.org", "Hucha casa", "--kind", "savings"]
        assert cli.main(args) == 1
        assert "Ya existe" in capsys.readouterr().err

    def test_password_is_not_a_command_line_argument(self, seed) -> None:
        with pytest.raises(SystemExit):
            cli.main(["users", "set-password", "raul@example.org", PASSWORD])
