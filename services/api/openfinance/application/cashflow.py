"""Flujo de caja de quien mira: dinero líquido por mes (ADR-0025, OF-1502).

Solo cuentas bancarias y efectivo que ve (ADR-0013) y que van en la moneda del hogar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from openfinance.application.errors import InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.cashflow import DEFAULT_MONTHS, MAX_MONTHS, MonthFlow, flow_of
from openfinance.domain.insights import Month, by_month
from openfinance.domain.ledger import AccountType
from openfinance.domain.shared import Currency, Money
from openfinance.domain.workspaces import Actor

LIQUID = (AccountType.BANK, AccountType.CASH)


@dataclass(frozen=True, slots=True)
class CashFlow:
    currency: Currency
    months: list[MonthFlow]
    accounts: int
    """Cuentas líquidas que entran en las cifras."""
    excluded_foreign: int
    """Cuentas líquidas en otra moneda, fuera de las cifras."""


def cash_flow(uow: UnitOfWork, actor: Actor, today: date, count: int = DEFAULT_MONTHS) -> CashFlow:
    if not 1 <= count <= MAX_MONTHS:
        raise InvalidRequestError(f"Elige entre 1 y {MAX_MONTHS} meses")
    household = uow.households.get(actor.household_id)
    if household is None:
        raise NotFoundError("Hogar no encontrado")
    currency = household.currency
    liquid = [a for a in visible_accounts(uow, actor) if a.type in LIQUID]
    counted = [a for a in liquid if a.currency == currency]
    ids = [a.id for a in counted]
    current = Month.of(today)
    first = current.shift(-(count - 1))
    by = (
        by_month(uow.transactions.in_range(actor.household_id, ids, first.start, current.end))
        if ids
        else {}
    )
    opening = sum((a.opening_balance.amount for a in counted), Decimal(0))

    def end_balance(month: Month) -> Money:
        sums = (
            uow.transactions.balances(
                actor.household_id,
                ids,
                until=datetime.combine(date(month.year, month.month, month.days), time.max),
            )
            if ids
            else {}
        )
        return Money.of(opening + sum(sums.values(), Decimal(0)), currency)

    months: list[MonthFlow] = []
    for i in range(count):
        month = first.shift(i)
        income, contributions, spending, savings, transfers = flow_of(by.get(month, []), currency)
        months.append(
            MonthFlow(
                month,
                income,
                contributions,
                spending,
                savings,
                transfers,
                end_balance(month),
                is_partial=month == current,
            )
        )
    return CashFlow(currency, months, len(counted), len(liquid) - len(counted))
