"""Previsión de saldo a partir de los pagos programados (ADR-0021, OF-1202). Funciones puras.

La previsión nunca cambia un saldo real: parte del saldo de hoy y suma, día a día, lo que está
pendiente. Lo atrasado no se suma (puede que no llegue) y lo ya cobrado ya está en el saldo.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from openfinance.domain.schedule import Occurrence, OccurrenceStatus
from openfinance.domain.shared import Money


@dataclass(frozen=True, slots=True)
class BalancePoint:
    day: date
    balance: Money
    """El saldo al acabar ese día."""


@dataclass(frozen=True, slots=True)
class Forecast:
    start: Money
    points: list[BalancePoint]
    """Hoy y cada día en que el saldo cambia, en orden."""
    lowest: BalancePoint
    first_negative: date | None
    """El primer día en que el saldo queda por debajo de cero, si llega a pasar."""
    end: Money


def forecast(
    balance: Money, occurrences: Iterable[Occurrence], today: date, until: date
) -> Forecast:
    """El saldo previsto de ``today`` a ``until`` (ambos incluidos)."""
    by_day: dict[date, Money] = defaultdict(lambda: Money.zero(balance.currency))
    for o in occurrences:
        if o.status is not OccurrenceStatus.PENDING or not today <= o.due <= until:
            continue
        by_day[o.due] = by_day[o.due] + o.amount
    points = [BalancePoint(today, balance + by_day.pop(today, Money.zero(balance.currency)))]
    current = points[0].balance
    for day in sorted(by_day):
        current = current + by_day[day]
        points.append(BalancePoint(day, current))
    lowest = min(points, key=lambda p: (p.balance.amount, p.day))
    first_negative = next((p.day for p in points if p.balance.is_negative), None)
    return Forecast(balance, points, lowest, first_negative, current)


def combine(forecasts: Iterable[Forecast], today: date) -> Forecast:
    """La suma de varias previsiones de la misma moneda (los días de cada una se unen)."""
    items = list(forecasts)
    if not items:
        raise ValueError("Nada que combinar")
    zero = Money.zero(items[0].start.currency)
    days = sorted({p.day for f in items for p in f.points} | {today})
    totals: dict[date, Money] = {}
    state: list[Money] = [f.start for f in items]
    pending = [list(f.points) for f in items]
    for day in days:
        for i, points in enumerate(pending):
            while points and points[0].day <= day:
                state[i] = points.pop(0).balance
        totals[day] = sum(state, zero)
    points = [BalancePoint(d, totals[d]) for d in days]
    lowest = min(points, key=lambda p: (p.balance.amount, p.day))
    first_negative = next((p.day for p in points if p.balance.is_negative), None)
    start = sum((f.start for f in items), zero)
    return Forecast(start, points, lowest, first_negative, points[-1].balance)
