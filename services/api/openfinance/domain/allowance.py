"""«Hoy podéis gastar»: cuánto se puede gastar al día sin llegar justos a la próxima entrada de
dinero (ADR-0021, OF-1205). Función pura.

Es un cálculo honesto, no una promesa: al saldo se le restan los pagos programados que aún
están por venir hasta la próxima entrada esperada (o hasta fin de mes si no hay ninguna) y lo
que queda se reparte entre los días que faltan. Sin saldo suficiente, el reparto es cero.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum

from openfinance.domain.schedule import Occurrence, OccurrenceStatus
from openfinance.domain.shared import Money


class Horizon(StrEnum):
    INCOME = "income"
    """Hasta la próxima entrada de dinero esperada."""
    MONTH_END = "month_end"
    """Hasta fin de mes: no hay ninguna entrada esperada antes."""


@dataclass(frozen=True, slots=True)
class Allowance:
    balance: Money
    committed: Money
    """Lo que está por pagar hasta el horizonte (positivo)."""
    available: Money
    """Saldo menos lo comprometido; negativo si no llega."""
    per_day: Money
    """Lo que se puede gastar cada día (cero si no llega), redondeado hacia abajo al céntimo."""
    days: int
    until: date
    """El día en que acaba el cálculo: la entrada de dinero o el último día del mes."""
    horizon: Horizon
    pending: list[Occurrence]
    """Los pagos que se han tenido en cuenta, por fecha."""
    next_income: Occurrence | None

    @property
    def short(self) -> bool:
        return self.available.is_negative


def month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def allowance(balance: Money, occurrences: Iterable[Occurrence], today: date) -> Allowance:
    """Lo que se puede gastar hoy y cada día hasta el horizonte.

    ``occurrences`` son las de los pagos programados; solo cuentan las pendientes (lo atrasado
    puede que no llegue y lo cobrado ya está en el saldo).
    """
    zero = Money.zero(balance.currency)
    pending = sorted(
        (
            o
            for o in occurrences
            if o.status is OccurrenceStatus.PENDING
            and o.due >= today
            and o.amount.currency == zero.currency
        ),
        key=lambda o: (o.due, str(o.payment_id)),
    )
    income = next((o for o in pending if o.amount.amount > 0 and o.due > today), None)
    if income is not None:
        until, horizon = income.due, Horizon.INCOME
        # El día de la entrada ya llega dinero: solo cuentan los pagos anteriores.
        counted = [o for o in pending if o.amount.amount < 0 and o.due < until]
        days = (until - today).days
    else:
        until, horizon = month_end(today), Horizon.MONTH_END
        counted = [o for o in pending if o.amount.amount < 0 and o.due <= until]
        days = (until - today).days + 1
    committed = sum((-o.amount for o in counted), zero)
    available = balance - committed
    spendable = max(available.amount, Decimal(0))
    per_day = Money.of(
        (spendable / days).quantize(Decimal("0.01"), rounding=ROUND_FLOOR), balance.currency
    )
    return Allowance(balance, committed, available, per_day, days, until, horizon, counted, income)
