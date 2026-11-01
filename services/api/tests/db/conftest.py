from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from openfinance.api.deps import get_hasher, get_login_throttle
from openfinance.application.households import (
    BootstrapRequest,
    NewAccount,
    NewMember,
    bootstrap_household,
)
from openfinance.domain.ledger import AccountKind, Institution, Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId
from openfinance.infrastructure.db import Base
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from openfinance.infrastructure.db.session import get_session_factory
from openfinance.infrastructure.throttle import LoginThrottle
from openfinance.main import create_app

PASSWORD = "contraseña-de-prueba"
CSRF = {"X-Requested-With": "OpenFinance"}


class FakeHasher:
    """Rápido y determinista; Argon2 se prueba por separado."""

    def hash(self, password: str) -> str:
        return f"fake${password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"fake${password}"

    def dummy_verify(self, password: str) -> None:
        return None

    async def averify(self, password_hash: str | None, password: str) -> bool:
        return password_hash is not None and self.verify(password_hash, password)


@pytest.fixture
def engine(tmp_path) -> Iterator[Engine]:
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    eng = create_engine(url)
    if eng.dialect.name == "sqlite":

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _):  # type: ignore[no-untyped-def]
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@dataclass
class Seed:
    raul: object
    elena: object
    ana: object
    joint: object
    raul_personal: object
    elena_personal: object
    other_joint: object


def _tx(account, amount, desc, when, kind=TransactionKind.EXPENSE, member=None, category=None):
    return Transaction(
        id=TransactionId(uuid4()),
        household_id=account.household_id,
        account_id=account.id,
        booked_at=when,
        value_date=when.date(),
        description=desc,
        amount=Money.of(amount, "EUR"),
        kind=kind,
        member_id=member,
        category_id=category,
    )


@pytest.fixture
def seed(session_factory) -> Seed:
    hasher = FakeHasher()
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        bootstrap_household(
            uow,
            hasher,
            BootstrapRequest(
                "Nuestra casa",
                [
                    NewMember("Raúl", "raul@example.org", PASSWORD),
                    NewMember("Elena", "elena@example.org", PASSWORD),
                ],
                [
                    NewAccount("Cuenta conjunta", Institution.REVOLUT, AccountKind.JOINT, "100.00"),
                    NewAccount(
                        "Bankinter Raúl", Institution.BANKINTER, AccountKind.PERSONAL, "500.00",
                        owner_email="raul@example.org",
                    ),
                    NewAccount(
                        "Bankinter Elena", Institution.BANKINTER, AccountKind.PERSONAL, "700.00",
                        owner_email="elena@example.org",
                    ),
                ],
            ),
        )  # fmt: skip
        bootstrap_household(
            uow,
            hasher,
            BootstrapRequest(
                "Vecinos",
                [NewMember("Ana", "ana@example.org", PASSWORD)],
                [NewAccount("Su conjunta", Institution.REVOLUT, AccountKind.JOINT, "50.00")],
            ),
        )
        raul = uow.users.get_by_email("raul@example.org")
        elena = uow.users.get_by_email("elena@example.org")
        ana = uow.users.get_by_email("ana@example.org")
        house = uow.households.households_of(raul.id)[0]
        by_name = {a.name: a for a in uow.accounts.for_household(house)}
        joint = by_name["Cuenta conjunta"]
        raul_p, elena_p = by_name["Bankinter Raúl"], by_name["Bankinter Elena"]
        other = uow.accounts.for_household(uow.households.households_of(ana.id)[0])[0]
        super_ = next(c.id for c in uow.categories.for_household(house) if c.slug == "super")

        d = datetime  # hora local del extracto
        for t in [
            _tx(joint, "1600.00", "Payment from Raul", d(2026, 10, 1, 8), TransactionKind.CONTRIBUTION, raul.id),  # noqa: E501
            _tx(joint, "-300.00", "To pocket Ahorro", d(2026, 10, 2, 7), TransactionKind.SAVINGS_TRANSFER),  # noqa: E501
            _tx(joint, "-87.34", "Mercadona", d(2026, 10, 3, 19), category=super_),
            _tx(joint, "-25.40", "Glovo 50% dto", d(2026, 10, 7, 21)),
            _tx(joint, "-60.00", "Mercadona", d(2026, 9, 28, 10), category=super_),
            _tx(raul_p, "-1600.00", "Aportación casa", d(2026, 10, 1, 7, 59), TransactionKind.CONTRIBUTION, raul.id),  # noqa: E501
            _tx(elena_p, "-42.00", "Peluquería", d(2026, 10, 9, 17)),
            _tx(other, "-10.00", "Mercadona vecinos", d(2026, 10, 3, 9)),
        ]:  # fmt: skip
            uow.transactions.add(t)
        uow.commit()
        return Seed(raul, elena, ana, joint, raul_p, elena_p, other)


@pytest.fixture
def app(session_factory):
    application = create_app()
    application.dependency_overrides[get_session_factory] = lambda: session_factory
    application.dependency_overrides[get_hasher] = FakeHasher
    throttle = LoginThrottle(5, 20, timedelta(minutes=15))
    application.dependency_overrides[get_login_throttle] = lambda: throttle
    return application


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app, headers=CSRF)


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


@pytest.fixture
def as_raul(app, seed) -> TestClient:
    c = TestClient(app, headers=CSRF)
    assert login(c, "raul@example.org").status_code == 200
    return c


@pytest.fixture
def as_elena(app, seed) -> TestClient:
    c = TestClient(app, headers=CSRF)
    assert login(c, "elena@example.org").status_code == 200
    return c


@pytest.fixture
def as_ana(app, seed) -> TestClient:
    c = TestClient(app, headers=CSRF)
    assert login(c, "ana@example.org").status_code == 200
    return c


__all__ = ["CSRF", "PASSWORD", "FakeHasher", "date", "login"]
