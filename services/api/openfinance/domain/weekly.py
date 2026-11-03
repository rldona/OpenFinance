"""Resumen semanal: qué semana es y cuánto cambió el gasto (ADR-0023, OF-1303)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

TOP_CATEGORIES = 3
UPCOMING_DAYS = 7


def last_full_week(today: date) -> tuple[date, date]:
    """El lunes y el domingo de la última semana completa antes de ``today``.

    En lunes es la semana que acaba de terminar; el resto de días, la anterior a la actual.
    """
    this_monday = today - timedelta(days=today.weekday())
    return this_monday - timedelta(days=7), this_monday - timedelta(days=1)


def week_key(today: date) -> str:
    """La semana ISO de hoy: es lo que evita enviar el resumen dos veces."""
    iso = today.isocalendar()
    return f"weekly:{iso.year}-W{iso.week:02d}"


def percent_change(current: Decimal, previous: Decimal) -> int | None:
    """Cambio en % respecto a la semana anterior, redondeado; ``None`` si no hay base."""
    if previous <= 0:
        return None
    return int(((current - previous) / previous * 100).quantize(Decimal(1), ROUND_HALF_UP))
