"""OF-905: los saldos se suman en SQL, sin cargar los movimientos."""

from dataclasses import replace
from decimal import Decimal

from sqlalchemy import event

from openfinance.application.ledger import list_accounts
from openfinance.domain.ledger import account_balance
from openfinance.domain.workspaces import Actor
from openfinance.infrastructure.db.repositories import SqlUnitOfWork


def _actor(seed) -> Actor:
    return Actor(seed.raul.id, seed.joint.household_id)


def test_sql_sum_matches_the_domain_balance(session_factory, seed) -> None:
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        for account in (seed.joint, seed.raul_personal, seed.other_joint):
            txns = uow.transactions.for_account(account.household_id, account.id)
            sums = uow.transactions.balances(account.household_id, [account.id])
            expected = account_balance(account, txns).amount - account.opening_balance.amount
            assert sums.get(account.id, Decimal(0)) == expected


def test_does_not_load_the_transactions(session_factory, seed, engine) -> None:
    statements: list[str] = []

    def record(_conn, _cur, statement, *_args) -> None:  # type: ignore[no-untyped-def]
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    with session_factory() as s:
        views = list_accounts(SqlUnitOfWork(s), _actor(seed))
    event.remove(engine, "before_cursor_execute", record)

    assert len(views) == 2
    # Una consulta de cuentas y una de saldos, no una por cuenta con todos sus movimientos.
    sums = [x for x in statements if "sum(" in x.lower()]
    assert len(sums) == 1
    assert len(statements) <= 3


def test_other_households_are_not_summed(session_factory, seed) -> None:
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        other = uow.transactions.balances(seed.joint.household_id, [seed.other_joint.id])
        assert other == {}
        assert uow.transactions.balances(seed.joint.household_id, []) == {}


def test_voided_movements_do_not_count(session_factory, seed) -> None:
    with session_factory() as s:
        uow = SqlUnitOfWork(s)
        before = uow.transactions.balances(seed.joint.household_id, [seed.joint.id])
        t = uow.transactions.for_account(seed.joint.household_id, seed.joint.id)[0]
        uow.transactions.save(replace(t, voided=True))
        after = uow.transactions.balances(seed.joint.household_id, [seed.joint.id])
        assert after[seed.joint.id] == before[seed.joint.id] - t.amount.amount


def test_confirming_an_import_flushes_once_for_all_the_rows(as_raul, seed) -> None:
    from sqlalchemy.orm import Session

    from tests.db.test_imports_api import commit, upload

    preview = upload(as_raul, seed.joint.id).json()
    assert preview["new_count"] == 10

    flushes: list[int] = []

    def count(session, _context) -> None:  # type: ignore[no-untyped-def]
        flushes.append(len(session.new))

    event.listen(Session, "after_flush", count)
    try:
        assert commit(as_raul, preview["id"]).status_code == 200
    finally:
        event.remove(Session, "after_flush", count)

    # Las 10 filas nuevas entran en un único flush, no uno por fila.
    assert max(flushes) >= 10
    assert len([n for n in flushes if n >= 10]) == 1
