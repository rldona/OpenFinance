"""Patrimonio neto de quien mira, hoy y a fin de cada mes (ADR-0025, OF-1501).

Solo las cuentas que ve (ADR-0013). Las de otra moneda se convierten con el tipo de cambio
más reciente anterior o igual a cada fecha; sin tipo, esa cuenta no entra en esa fecha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from openfinance.application.conversion import converter
from openfinance.application.errors import NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.ledger import Account, AccountType
from openfinance.domain.networth import (
    Holding,
    WorthPoint,
    by_type,
    history_dates,
    worth_point,
)
from openfinance.domain.shared import Money
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class AccountWorth:
    account: Account
    balance: Money
    """En la moneda de la cuenta."""
    value: Money | None
    """En la del hogar; ``None`` si falta el tipo de cambio."""


@dataclass(frozen=True, slots=True)
class NetWorth:
    currency_code: str
    today: WorthPoint
    history: list[WorthPoint]
    """Fines de mes y hoy, de más antiguo a más nuevo."""
    accounts: list[AccountWorth]
    by_type: dict[AccountType, Money]
    missing_rates: list[str]
    """Monedas con alguna cuenta que no entra hoy por falta de tipo de cambio (las fechas
    pasadas sin tipo se ven en ``excluded`` de cada punto)."""


def net_worth(uow: UnitOfWork, actor: Actor, today: date) -> NetWorth:
    household = uow.households.get(actor.household_id)
    if household is None:
        raise NotFoundError("Hogar no encontrado")
    reference = household.currency
    accounts = visible_accounts(uow, actor)
    conv = converter(uow, actor.household_id)
    ids = [a.id for a in accounts]

    def holdings(on: date) -> list[tuple[Account, Money, Money | None]]:
        sums = (
            uow.transactions.balances(actor.household_id, ids, until=datetime.combine(on, time.max))
            if ids
            else {}
        )
        out = []
        for a in accounts:
            balance = a.opening_balance + Money.of(sums.get(a.id, Decimal(0)), a.currency)
            out.append((a, balance, conv.convert(balance, on)))
        return out

    history: list[WorthPoint] = []
    latest: list[tuple[Account, Money, Money | None]] = []
    for on in history_dates(today):
        latest = holdings(on)
        history.append(worth_point(on, [Holding(a.type, v) for a, _, v in latest], reference))
    final = [Holding(a.type, v) for a, _, v in latest]
    missing = {a.currency.code for a, _, v in latest if v is None}
    return NetWorth(
        currency_code=reference.code,
        today=history[-1],
        history=history,
        accounts=[AccountWorth(a, b, v) for a, b, v in latest],
        by_type=by_type(final, reference),
        missing_rates=sorted(missing),
    )
