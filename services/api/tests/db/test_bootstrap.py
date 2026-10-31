import pytest

from openfinance.application.errors import ConflictError, InvalidRequestError
from openfinance.application.households import (
    BootstrapRequest,
    NewAccount,
    NewMember,
    bootstrap_household,
)
from openfinance.cli import collect_request
from openfinance.domain.ledger import AccountKind, Institution
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from openfinance.infrastructure.security import Argon2PasswordHasher
from tests.db.conftest import PASSWORD, FakeHasher


def request(*members, accounts=()):
    return BootstrapRequest("Casa", list(members), list(accounts))


def test_duplicated_email_is_a_conflict(session_factory, seed) -> None:
    with session_factory() as s, pytest.raises(ConflictError):
        bootstrap_household(
            SqlUnitOfWork(s), FakeHasher(), request(NewMember("R", "RAUL@example.org", PASSWORD))
        )


def test_personal_account_owner_must_be_member(session_factory) -> None:
    acc = NewAccount("X", Institution.BANKINTER, AccountKind.PERSONAL, owner_email="x@y.org")
    req = request(NewMember("R", "r@e.org", PASSWORD), accounts=[acc])
    with session_factory() as s, pytest.raises(InvalidRequestError, match="titular"):
        bootstrap_household(SqlUnitOfWork(s), FakeHasher(), req)


def test_short_password_is_rejected(session_factory) -> None:
    with session_factory() as s, pytest.raises(InvalidRequestError, match="contraseña"):
        bootstrap_household(SqlUnitOfWork(s), FakeHasher(), request(NewMember("R", "r@e.org", "x")))


def test_failed_bootstrap_leaves_nothing_behind(session_factory) -> None:
    bad = NewAccount("X", Institution.BANKINTER, AccountKind.PERSONAL, owner_email="x@y.org")
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        with pytest.raises(InvalidRequestError):
            bootstrap_household(
                uow, FakeHasher(), request(NewMember("R", "r@e.org", PASSWORD), accounts=[bad])
            )
    with session_factory() as s:
        assert SqlUnitOfWork(s).users.get_by_email("r@e.org") is None


def test_cli_collects_household_two_people_and_accounts() -> None:
    answers = iter([
        "Nuestra casa",
        "Raúl", "raul@example.org",
        "Elena", "elena@example.org",
        "", "1234.56",   # conjunta: nombre por defecto y saldo
        "s", "200",      # Bankinter Raúl
        "n",             # sin Bankinter Elena
    ])  # fmt: skip
    secrets = iter(
        ["corta", "una-clave-larga", "una-clave-larga", "otra-clave-larga", "otra-clave-larga"]
    )
    req = collect_request(lambda _: next(answers), lambda _: next(secrets))
    assert req.household_name == "Nuestra casa"
    assert [m.display_name for m in req.members] == ["Raúl", "Elena"]
    assert req.members[0].password == "una-clave-larga"
    assert [(a.name, a.kind, a.opening_balance) for a in req.accounts] == [
        ("Cuenta conjunta", AccountKind.JOINT, "1234.56"),
        ("Bankinter Raúl", AccountKind.PERSONAL, "200"),
    ]
    assert req.accounts[1].owner_email == "raul@example.org"


def test_argon2_hasher() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash(PASSWORD)
    assert hashed.startswith("$argon2id$")
    assert hasher.verify(hashed, PASSWORD)
    assert not hasher.verify(hashed, "otra")
    assert not hasher.verify("no-es-un-hash", PASSWORD)
