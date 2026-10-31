"""Consultas de cuentas y movimientos (OF-102, OF-103)."""

from __future__ import annotations

from dataclasses import dataclass

from openfinance.application.errors import NotFoundError
from openfinance.application.ports import TransactionQuery, UnitOfWork
from openfinance.domain.ledger import Account, AccountKind, Transaction, account_balance
from openfinance.domain.shared import Money
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class AccountView:
    account: Account
    balance: Money


def visible_accounts(uow: UnitOfWork, actor: Actor) -> list[Account]:
    return [
        a for a in uow.accounts.for_household(actor.household_id) if a.visible_to(actor.user_id)
    ]


def list_accounts(uow: UnitOfWork, actor: Actor) -> list[AccountView]:
    return [
        AccountView(a, account_balance(a, uow.transactions.for_account(actor.household_id, a.id)))
        for a in visible_accounts(uow, actor)
    ]


def list_transactions(uow: UnitOfWork, actor: Actor, query: TransactionQuery) -> list[Transaction]:
    accounts = visible_accounts(uow, actor)
    if query.shared_only:
        accounts = [a for a in accounts if a.kind in (AccountKind.JOINT, AccountKind.SAVINGS)]
    ids = [a.id for a in accounts]
    if query.account_id is not None:
        if query.account_id not in ids:
            raise NotFoundError("Cuenta no encontrada")
        ids = [query.account_id]
    if not ids:
        return []
    return uow.transactions.search(actor.household_id, ids, query)
