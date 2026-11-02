"""Previsión de saldo del hogar y de cada cuenta (ADR-0021, OF-1202).

Solo entran las cuentas que ve quien consulta (ADR-0013) y que son de efectivo: las de tipo
``card`` y ``loan`` no son dinero disponible y se dejan fuera. Cada moneda se suma aparte: no
se mezclan monedas sin una tasa, y la previsión no la inventa.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from openfinance.application.errors import InvalidRequestError
from openfinance.application.ledger import balances_of, visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.application.schedule import MAX_HORIZON_DAYS, list_schedule
from openfinance.domain.forecast import Forecast, combine, forecast
from openfinance.domain.ledger import Account, AccountType
from openfinance.domain.schedule import Occurrence
from openfinance.domain.shared import Currency
from openfinance.domain.shared.ids import AccountId
from openfinance.domain.workspaces import Actor

NOT_CASH = (AccountType.CARD, AccountType.LOAN)


@dataclass(frozen=True, slots=True)
class AccountForecast:
    account: Account
    forecast: Forecast


@dataclass(frozen=True, slots=True)
class CurrencyForecast:
    currency: Currency
    forecast: Forecast


@dataclass(frozen=True, slots=True)
class ForecastView:
    until: date
    accounts: list[AccountForecast]
    totals: list[CurrencyForecast]


def household_forecast(uow: UnitOfWork, actor: Actor, today: date, days: int) -> ForecastView:
    if not 1 <= days <= MAX_HORIZON_DAYS:
        raise InvalidRequestError(f"El horizonte va de 1 a {MAX_HORIZON_DAYS} días")
    until = today + timedelta(days=days)
    accounts = [a for a in visible_accounts(uow, actor) if a.type not in NOT_CASH]
    balances = balances_of(uow, actor, accounts)
    by_account: dict[AccountId, list[Occurrence]] = defaultdict(list)
    for view in list_schedule(uow, actor, today, days):
        by_account[view.payment.account_id].extend(view.occurrences)

    results = [
        AccountForecast(a, forecast(balances[a.id], by_account[a.id], today, until))
        for a in accounts
    ]
    grouped: dict[Currency, list[Forecast]] = defaultdict(list)
    for r in results:
        grouped[r.account.currency].append(r.forecast)
    totals = [
        CurrencyForecast(currency, combine(items, today))
        for currency, items in sorted(grouped.items(), key=lambda kv: kv[0].code)
    ]
    return ForecastView(until, results, totals)
