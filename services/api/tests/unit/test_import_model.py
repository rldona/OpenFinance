"""Modelo de importación: huellas estables y saldo final del extracto."""

# ruff: noqa: DTZ001 - los extractos traen hora local, sin zona

from datetime import date, datetime

import pytest

from openfinance.domain.imports import ImportedRow, ParseResult, TransactionKind, fingerprint
from openfinance.domain.shared import Money

WHEN = datetime(2026, 10, 1, 10, 0, 0)
EUR = Money.of("-12.30", "EUR")


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            ("cuenta-1", WHEN, EUR, "Café Central", 0),
            "c3cdc23df46da52577f3d8710f724ac4ebcedae7381c61c3b930436995b4fd78",
        ),
        (
            ("cuenta-1", WHEN, EUR, "Café Central", 1),
            "d643ff7500fe73f6a3daf45fd584e3c360c28342c4f35557a38f4b7e377b0e56",
        ),
        (
            ("otra", datetime(2026, 1, 2), Money.of("1500", "EUR"), "  transfer   from Raúl ", 0),
            "7b394801dacf028a7b384049ce0fd34a60f645db4f1f586f9b8e09b26e5e242d",
        ),
    ],
)
def test_fingerprints_already_stored_never_change(args, expected) -> None:
    """Las huellas guardadas en la base de datos no pueden cambiar: se duplicarían filas."""
    assert fingerprint(*args) == expected


def test_empty_discriminator_keeps_the_historic_hash() -> None:
    assert fingerprint("cuenta-1", WHEN, EUR, "Café Central", 0, discriminator="") == (
        "c3cdc23df46da52577f3d8710f724ac4ebcedae7381c61c3b930436995b4fd78"
    )


def test_discriminator_changes_the_hash() -> None:
    a = fingerprint("cuenta-1", WHEN, EUR, "Café Central", 0, discriminator="100.00")
    b = fingerprint("cuenta-1", WHEN, EUR, "Café Central", 0, discriminator="87.70")
    assert a != b
    assert a != fingerprint("cuenta-1", WHEN, EUR, "Café Central", 0)


def _row(line: int, booked: datetime, balance: str | None) -> ImportedRow:
    return ImportedRow(
        booked_at=booked,
        value_date=date(2026, 10, 1),
        description="x",
        amount=EUR,
        bank_type="",
        suggested_kind=TransactionKind.EXPENSE,
        fingerprint=str(line),
        balance_after=Money.of(balance, "EUR") if balance else None,
        line=line,
    )


def test_closing_balance_is_the_last_row_in_balance_order() -> None:
    # La última fila aplicada manda aunque empezara antes que otra (orden de finalización).
    result = ParseResult(
        rows=[
            _row(2, datetime(2026, 10, 2), "50.00"),
            _row(3, datetime(2026, 10, 1), "37.70"),
            _row(4, datetime(2026, 10, 3), None),
        ]
    )
    assert result.closing_balance == Money.of("37.70", "EUR")


def test_closing_balance_without_balances() -> None:
    assert ParseResult().closing_balance is None
