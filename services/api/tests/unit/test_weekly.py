"""OF-1303: qué semana se resume y cuánto cambia."""

from datetime import date
from decimal import Decimal

import pytest

from openfinance.domain.weekly import last_full_week, percent_change, week_key


@pytest.mark.parametrize(
    ("today", "start", "end"),
    [
        (
            date(2026, 11, 2),
            date(2026, 10, 26),
            date(2026, 11, 1),
        ),  # lunes: la que acaba de terminar
        (
            date(2026, 11, 4),
            date(2026, 10, 26),
            date(2026, 11, 1),
        ),  # miércoles: la anterior a la actual
        (
            date(2026, 11, 8),
            date(2026, 10, 26),
            date(2026, 11, 1),
        ),  # domingo: aún no ha terminado la actual
        (date(2027, 1, 1), date(2026, 12, 21), date(2026, 12, 27)),  # cruza el año
    ],
)
def test_the_last_full_week_is_monday_to_sunday(today: date, start: date, end: date) -> None:
    assert last_full_week(today) == (start, end)
    assert start.weekday() == 0 and end.weekday() == 6


def test_the_week_key_is_the_iso_week_of_today() -> None:
    assert week_key(date(2026, 11, 2)) == "weekly:2026-W45"
    assert week_key(date(2026, 11, 8)) == "weekly:2026-W45"
    assert week_key(date(2027, 1, 1)) == "weekly:2026-W53"  # el año ISO no es el natural


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        ("120", "100", 20),
        ("50", "100", -50),
        ("100", "100", 0),
        ("100.50", "100", 1),
        ("5", "0", None),
        ("0", "0", None),
    ],
)
def test_percent_change(current: str, previous: str, expected: int | None) -> None:
    assert percent_change(Decimal(current), Decimal(previous)) == expected
