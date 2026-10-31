from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

_CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")

# Decimales de la unidad monetaria menor (ISO 4217). Las no listadas usan 2.
_MINOR_UNITS: dict[str, int] = {
    "EUR": 2,
    "USD": 2,
    "GBP": 2,
    "CHF": 2,
    "JPY": 0,
    "KRW": 0,
    "KWD": 3,
    "BHD": 3,
}
_DEFAULT_MINOR_UNITS = 2


class CurrencyMismatchError(ValueError):
    """Se intentó operar con importes de monedas distintas."""


@dataclass(frozen=True, slots=True)
class Currency:
    code: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not _CURRENCY_CODE.match(self.code):
            raise ValueError(f"Código de moneda ISO 4217 no válido: {self.code!r}")

    @property
    def minor_units(self) -> int:
        return _MINOR_UNITS.get(self.code, _DEFAULT_MINOR_UNITS)

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class Money:
    """Importe monetario exacto. Nunca se construye a partir de float."""

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if isinstance(self.amount, bool) or not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount debe ser Decimal; usa Money.of() con str o int")
        if not self.amount.is_finite():
            raise ValueError("Money.amount debe ser un número finito")
        if not isinstance(self.currency, Currency):
            raise TypeError("Money.currency debe ser Currency")
        quantum = Decimal(1).scaleb(-self.currency.minor_units)
        object.__setattr__(self, "amount", self.amount.quantize(quantum, rounding=ROUND_HALF_EVEN))

    @classmethod
    def of(cls, amount: str | int | Decimal, currency: str | Currency) -> Money:
        if isinstance(amount, float | bool):
            raise TypeError("No se admiten float ni bool como importe")
        try:
            value = amount if isinstance(amount, Decimal) else Decimal(amount)
        except InvalidOperation as exc:
            raise ValueError(f"Importe no válido: {amount!r}") from exc
        cur = currency if isinstance(currency, Currency) else Currency(currency)
        return cls(value, cur)

    @classmethod
    def zero(cls, currency: str | Currency) -> Money:
        return cls.of(0, currency)

    def _check_same_currency(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError("Solo se puede operar entre Money")
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"No se puede operar {self.currency} con {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    @property
    def is_zero(self) -> bool:
        return self.amount.is_zero()

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"
