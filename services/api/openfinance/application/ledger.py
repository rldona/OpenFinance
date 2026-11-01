"""Consultas de cuentas y movimientos (OF-102, OF-103)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from openfinance.application.errors import NotFoundError
from openfinance.application.ports import TransactionQuery, UnitOfWork
from openfinance.domain.ledger import Account, AccountKind, Transaction
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class AccountView:
    account: Account
    balance: Money


def visible_accounts(uow: UnitOfWork, actor: Actor) -> list[Account]:
    return [
        a for a in uow.accounts.for_household(actor.household_id) if a.visible_to(actor.user_id)
    ]


def balances_of(uow: UnitOfWork, actor: Actor, accounts: list[Account]) -> dict[AccountId, Money]:
    """Saldo de varias cuentas con una sola consulta (suma en SQL, OF-905)."""
    sums = uow.transactions.balances(actor.household_id, [a.id for a in accounts])
    return {
        a.id: a.opening_balance + Money.of(sums.get(a.id, Decimal(0)), a.opening_balance.currency)
        for a in accounts
    }


def balance_of(uow: UnitOfWork, actor: Actor, account: Account) -> Money:
    return balances_of(uow, actor, [account])[account.id]


def list_accounts(uow: UnitOfWork, actor: Actor) -> list[AccountView]:
    accounts = visible_accounts(uow, actor)
    balances = balances_of(uow, actor, accounts)
    return [AccountView(a, balances[a.id]) for a in accounts]


def _account_ids(uow: UnitOfWork, actor: Actor, query: TransactionQuery) -> list[AccountId]:
    accounts = visible_accounts(uow, actor)
    if query.shared_only:
        accounts = [a for a in accounts if a.kind in (AccountKind.JOINT, AccountKind.SAVINGS)]
    if query.mine_only:
        accounts = [a for a in accounts if a.owner_id == actor.user_id]
    ids = [a.id for a in accounts]
    if query.account_id is not None:
        if query.account_id not in ids:
            raise NotFoundError("Cuenta no encontrada")
        ids = [query.account_id]
    return ids


def list_transactions(uow: UnitOfWork, actor: Actor, query: TransactionQuery) -> list[Transaction]:
    ids = _account_ids(uow, actor, query)
    if not ids:
        return []
    return uow.transactions.search(actor.household_id, ids, query)


@dataclass(frozen=True, slots=True)
class TransactionPage:
    items: list[Transaction]
    next_after: tuple[datetime, UUID] | None
    """Cursor de la página siguiente; ``None`` si esta es la última."""
    count: int
    """Movimientos que cumplen el filtro en total, no solo los de esta página."""
    total: Money
    """Suma de sus importes (con signo)."""


def page_transactions(uow: UnitOfWork, actor: Actor, query: TransactionQuery) -> TransactionPage:
    """Una página del listado (OF-803) con el total del filtro. Solo cuentas visibles."""
    household = uow.households.get(actor.household_id)
    if household is None:
        raise NotFoundError("Hogar no encontrado")
    ids = _account_ids(uow, actor, query)
    if not ids:
        return TransactionPage([], None, 0, Money.zero(household.currency))
    rows = uow.transactions.search(
        actor.household_id, ids, replace(query, limit=query.limit + 1, after=query.after)
    )
    page = rows[: query.limit]
    last = page[-1] if len(rows) > query.limit else None
    count, total = uow.transactions.totals(actor.household_id, ids, replace(query, after=None))
    return TransactionPage(
        page,
        (last.booked_at, last.id) if last else None,
        count,
        Money.of(total, household.currency),
    )
