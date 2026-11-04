"""Patrimonio neto: activos menos deudas en la moneda del hogar (ADR-0025, OF-1501).

Un saldo positivo es un activo y uno negativo una deuda, sea cual sea el tipo de cuenta: una
tarjeta con saldo negativo es lo que se debe y un descubierto también. Una cuenta cuyo saldo
no se puede convertir (falta el tipo de cambio) no entra: se cuenta aparte, nunca se inventa.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from openfinance.domain.ledger import AccountType
from openfinance.domain.shared import Currency, Money

HISTORY_MONTHS = 12
"""Fines de mes anteriores que se enseñan, además de hoy."""


@dataclass(frozen=True, slots=True)
class Holding:
    """Una cuenta en una fecha: su tipo y su saldo ya convertido (``None`` si no se pudo)."""

    type: AccountType
    value: Money | None


@dataclass(frozen=True, slots=True)
class WorthPoint:
    on: date
    assets: Money
    debts: Money
    """En positivo: cuánto se debe."""
    net: Money
    excluded: int
    """Cuentas que no entran en esta fecha por falta de tipo de cambio."""


def worth_point(on: date, holdings: Iterable[Holding], reference: Currency) -> WorthPoint:
    assets = Money.zero(reference)
    debts = Money.zero(reference)
    excluded = 0
    for h in holdings:
        if h.value is None:
            excluded += 1
        elif h.value.is_negative:
            debts = debts - h.value
        else:
            assets = assets + h.value
    return WorthPoint(on, assets, debts, assets - debts, excluded)


def by_type(holdings: Iterable[Holding], reference: Currency) -> dict[AccountType, Money]:
    """El neto de cada tipo de cuenta (solo los tipos con alguna cuenta convertible)."""
    totals: dict[AccountType, Money] = {}
    for h in holdings:
        if h.value is not None:
            totals[h.type] = totals.get(h.type, Money.zero(reference)) + h.value
    return totals


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def history_dates(today: date, count: int = HISTORY_MONTHS) -> list[date]:
    """Los ``count`` últimos fines de mes anteriores a hoy y hoy, de más antiguo a más nuevo."""
    dates: list[date] = []
    year, month = today.year, today.month
    for _ in range(count):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        dates.append(month_end(year, month))
    return [*reversed(dates), today]
