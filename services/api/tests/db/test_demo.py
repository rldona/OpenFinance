from datetime import date

import pytest
from fastapi.testclient import TestClient

from openfinance.application.errors import ConflictError
from openfinance.cli import main
from openfinance.demo import DEMO_PASSWORD, create_demo
from openfinance.domain.insights import Month
from openfinance.infrastructure.config import get_settings
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from tests.db.conftest import CSRF, FakeHasher


def test_demo_household_has_twelve_months_of_consistent_data(session_factory, app) -> None:
    with session_factory() as s:
        r = create_demo(SqlUnitOfWork(s), FakeHasher(), date(2026, 10, 31))
    assert r.months == ("2025-11", "2026-10")
    assert r.transactions > 300

    c = TestClient(app, headers=CSRF)
    login = c.post("/api/v1/auth/login", json={"email": r.emails[0], "password": DEMO_PASSWORD})
    assert login.status_code == 200
    t = c.get("/api/v1/insights/trends", params={"month": "2026-10"}).json()
    assert all(m["has_data"] for m in t["months"])
    assert c.get("/api/v1/transactions/uncategorized-count").json()["count"] == 3
    o = c.get("/api/v1/insights/month", params={"month": "2026-10"}).json()
    assert o["inflow"] == {"amount": "3000.00", "currency": "EUR"}
    assert len(o["categories"]) >= 8
    assert len(c.get("/api/v1/budgets").json()["items"]) == 10
    assert [g["name"] for g in c.get("/api/v1/goals").json()] == [
        "Fondo de emergencia",
        "Vacaciones de verano",
    ]


def test_demo_stops_today(session_factory) -> None:
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        r = create_demo(uow, FakeHasher(), date(2026, 10, 10))
        user = uow.users.get_by_email(r.emails[0])
        house = uow.households.households_of(user.id)[0]
        accounts = [a.id for a in uow.accounts.for_household(house)]
        rows = uow.transactions.in_range(house, accounts, Month(2000, 1).start, Month(2100, 1).end)
    assert max(t.booked_at.date() for t in rows) <= date(2026, 10, 10)


def test_demo_cannot_be_created_twice(session_factory) -> None:
    with session_factory() as s:
        create_demo(SqlUnitOfWork(s), FakeHasher(), date(2026, 10, 31))
    with session_factory() as s, pytest.raises(ConflictError):
        create_demo(SqlUnitOfWork(s), FakeHasher(), date(2026, 10, 31))


def test_demo_refuses_to_run_in_production(monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENFINANCE_ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        assert main(["demo"]) == 1
        assert "--force" in capsys.readouterr().err
    finally:
        get_settings.cache_clear()


def test_demo_is_all_or_nothing(session_factory, monkeypatch) -> None:
    from openfinance.infrastructure.db.repositories import SqlTransactionRepository

    def boom(*_):
        raise RuntimeError("fallo a mitad")

    monkeypatch.setattr(SqlTransactionRepository, "add", boom)
    with session_factory() as s, pytest.raises(RuntimeError):
        create_demo(SqlUnitOfWork(s), FakeHasher(), date(2026, 10, 31))
    with session_factory() as s:
        assert SqlUnitOfWork(s).users.get_by_email("raul@demo.openfinance") is None
