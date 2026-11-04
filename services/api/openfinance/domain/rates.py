"""Tipos de cambio manuales y conversión a la moneda del hogar (ADR-0019, OF-1008).

OpenFinance no consulta ninguna cotización en línea: los tipos los pone quien lleva la casa (o
vienen de un extracto). Sin tipo para una fecha, un importe **no se convierte**: se avisa en vez
de inventar un valor.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import WorkspaceId

RATE_DECIMALS = 8
MAX_RATE = Decimal("1000000")


class RateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExchangeRate:
    household_id: WorkspaceId
    currency: Currency
    on: date
    rate: Decimal
    """Cuántas unidades de la moneda del hogar vale 1 unidad de ``currency``."""
    source: str = "manual"

    def __post_init__(self) -> None:
        if self.source not in ("manual", "extracto"):
            raise RateError("El origen del tipo de cambio es «manual» o «extracto»")
        if not self.rate.is_finite() or self.rate <= 0 or self.rate > MAX_RATE:
            raise RateError("El tipo de cambio tiene que ser un número mayor que cero")
        if self.rate != self.rate.quantize(Decimal(1).scaleb(-RATE_DECIMALS)):
            raise RateError(f"El tipo de cambio admite como máximo {RATE_DECIMALS} decimales")


def check_foreign(reference: Currency, currency: Currency) -> None:
    if currency == reference:
        raise RateError(f"{currency} ya es la moneda del hogar: no necesita tipo de cambio")


@dataclass(frozen=True, slots=True)
class Converter:
    """Convierte a la moneda de referencia con el tipo más reciente anterior o igual a la fecha."""

    reference: Currency
    series: Mapping[str, Sequence[tuple[date, Decimal]]]
    """Por moneda, los tipos ordenados por fecha."""

    @classmethod
    def of(cls, reference: Currency, rates: Sequence[ExchangeRate]) -> Converter:
        grouped: dict[str, list[tuple[date, Decimal]]] = {}
        for r in rates:
            grouped.setdefault(r.currency.code, []).append((r.on, r.rate))
        return cls(reference, {k: sorted(v) for k, v in grouped.items()})

    def rate_on(self, currency: Currency, on: date) -> Decimal | None:
        series = self.series.get(currency.code)
        if not series:
            return None
        i = bisect_right([d for d, _ in series], on)
        return series[i - 1][1] if i else None

    def convert(self, money: Money, on: date) -> Money | None:
        """El importe en la moneda del hogar, o ``None`` si no hay tipo para esa fecha.
        Se redondea una sola vez, al final (``ROUND_HALF_EVEN`` en ``Money``)."""
        if money.currency == self.reference:
            return money
        rate = self.rate_on(money.currency, on)
        if rate is None:
            return None
        return Money.of(money.amount * rate, self.reference)
