"""«Hoy podéis gastar» con el dinero de la cuenta conjunta (ADR-0021, OF-1205).

Solo cuenta lo que es de los dos: las cuentas conjuntas de efectivo y banco, en la moneda del
hogar. Una cuenta personal (ni la propia) no entra, así que las dos personas ven la misma cifra.
Si faltan datos para que la cifra signifique algo, se dice y no se inventa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from openfinance.application.errors import NotFoundError
from openfinance.application.ledger import balances_of, visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.application.savings import BudgetView, list_budgets
from openfinance.application.schedule import list_schedule
from openfinance.domain.allowance import Allowance, allowance
from openfinance.domain.insights import Month
from openfinance.domain.ledger import AccountKind, AccountType
from openfinance.domain.savings import BudgetMode
from openfinance.domain.schedule import Occurrence, ScheduleId
from openfinance.domain.shared import Money
from openfinance.domain.workspaces import Actor

LOOKAHEAD_DAYS = 62
"""Hasta dónde se busca la próxima entrada de dinero si no cae en este mes."""
SPENDABLE_TYPES = (AccountType.BANK, AccountType.CASH)


class Status(StrEnum):
    OK = "ok"
    NO_BALANCE = "no_balance"
    """No hay ninguna cuenta conjunta de la que sacar el saldo."""
    NO_SCHEDULE = "no_schedule"
    """No hay pagos programados: sin ellos la cifra ignoraría lo que está por venir."""


@dataclass(frozen=True, slots=True)
class AllowanceView:
    status: Status
    allowance: Allowance | None
    names: dict[ScheduleId, str]
    """Nombre de cada pago que aparece en el cálculo."""
    envelopes: list[BudgetView]
    """Lo que queda en cada sobre este mes."""


def household_allowance(uow: UnitOfWork, actor: Actor, today: date) -> AllowanceView:
    household = uow.households.get(actor.household_id)
    if household is None:
        raise NotFoundError("Hogar no encontrado")
    accounts = [
        a
        for a in visible_accounts(uow, actor)
        if a.kind is AccountKind.JOINT
        and a.type in SPENDABLE_TYPES
        and a.currency == household.currency
    ]
    if not accounts:
        return AllowanceView(Status.NO_BALANCE, None, {}, [])
    ids = {a.id for a in accounts}
    views = [
        v
        for v in list_schedule(uow, actor, today, LOOKAHEAD_DAYS)
        if v.payment.account_id in ids and v.payment.active
    ]
    if not views:
        return AllowanceView(Status.NO_SCHEDULE, None, {}, [])
    balances = balances_of(uow, actor, accounts)
    balance = sum(balances.values(), Money.zero(household.currency))
    occurrences: list[Occurrence] = [o for v in views for o in v.occurrences]
    result = allowance(balance, occurrences, today)
    names = {v.payment.id: v.payment.name for v in views}
    envelopes = [
        b
        for b in list_budgets(uow, actor, Month.of(today), today)
        if b.budget.mode is BudgetMode.ENVELOPE
    ]
    return AllowanceView(Status.OK, result, names, envelopes)
