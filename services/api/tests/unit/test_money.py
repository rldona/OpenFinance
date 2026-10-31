from decimal import Decimal

import pytest

from openfinance.domain.shared import Currency, CurrencyMismatchError, Money


def test_builds_from_string_and_quantizes_to_minor_units() -> None:
    assert Money.of("10.005", "EUR").amount == Decimal("10.00")
    assert Money.of("10.015", "EUR").amount == Decimal("10.02")
    assert Money.of("1500.4", "JPY").amount == Decimal("1500")


@pytest.mark.parametrize("bad", [10.5, True])
def test_rejects_float_and_bool(bad: object) -> None:
    with pytest.raises(TypeError):
        Money.of(bad, "EUR")  # type: ignore[arg-type]


def test_rejects_non_finite_and_garbage() -> None:
    with pytest.raises(ValueError):
        Money.of("NaN", "EUR")
    with pytest.raises(ValueError):
        Money.of("diez", "EUR")


@pytest.mark.parametrize("code", ["eur", "EU", "EURO", "", "12A"])
def test_rejects_invalid_currency(code: str) -> None:
    with pytest.raises(ValueError):
        Currency(code)


def test_arithmetic_same_currency() -> None:
    total = Money.of("10.10", "EUR") + Money.of("0.20", "EUR")
    assert total == Money.of("10.30", "EUR")
    assert (total - Money.of("10.30", "EUR")).is_zero
    assert (-total).is_negative


def test_arithmetic_rejects_mixed_currencies() -> None:
    with pytest.raises(CurrencyMismatchError):
        Money.of(1, "EUR") + Money.of(1, "USD")


def test_is_immutable() -> None:
    money = Money.zero("EUR")
    with pytest.raises(AttributeError):
        money.amount = Decimal(1)  # type: ignore[misc]


def test_str() -> None:
    assert str(Money.of("3.5", "EUR")) == "3.50 EUR"
