"""Dividir un movimiento en partes con su categoría (OF-1003).

Un ticket de 87,34 € puede ser 60 € de supermercado y 27,34 € de hogar. La división es una capa
encima del movimiento: su importe, fecha y concepto no cambian, y los informes cuentan las
partes en lugar del total. Las partes suman siempre el importe original, al céntimo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from openfinance.domain.categories import CategoryId
from openfinance.domain.shared import Money

MIN_PARTS = 2
MAX_PARTS = 10
VALUE_SEPARATOR = "|"


class SplitError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SplitPart:
    amount: Money
    category_id: CategoryId


def validate_split(total: Money, parts: Sequence[SplitPart]) -> None:
    """Dos a diez partes, con el mismo signo que el total y que sumen exactamente el total."""
    if not MIN_PARTS <= len(parts) <= MAX_PARTS:
        raise SplitError(f"Un movimiento se divide en {MIN_PARTS} a {MAX_PARTS} partes")
    currency = total.currency
    for part in parts:
        if part.amount.currency != currency:
            raise SplitError("Todas las partes van en la moneda del movimiento")
        if part.amount.is_zero:
            raise SplitError("Una parte no puede ser de importe cero")
        if part.amount.is_negative != total.is_negative:
            raise SplitError("Todas las partes tienen el signo del movimiento")
    summed = Money.zero(currency)
    for part in parts:
        summed = summed + part.amount
    if summed != total:
        raise SplitError(
            f"Las partes suman {summed.amount} y el movimiento es de {total.amount}: "
            "tienen que sumar lo mismo"
        )


def encode_parts(parts: Sequence[SplitPart]) -> str | None:
    """Valor para el registro de cambios: «importe@categoría|importe@categoría» (o ``None``)."""
    if not parts:
        return None
    return VALUE_SEPARATOR.join(f"{p.amount.amount}@{p.category_id}" for p in parts)


def decode_parts(value: str | None, currency: str) -> list[SplitPart]:
    from uuid import UUID

    if not value:
        return []
    out: list[SplitPart] = []
    for item in value.split(VALUE_SEPARATOR):
        amount, _, category = item.partition("@")
        out.append(SplitPart(Money.of(Decimal(amount), currency), CategoryId(UUID(category))))
    return out
