"""Piezas comunes de los repositorios SQL."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from openfinance.application.errors import ConflictError

_AMOUNT_QUANTUM = Decimal("0.0001")
_CONFLICT = "Los datos han cambiado mientras guardabas; vuelve a intentarlo"


def _flush(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            "Los datos han cambiado mientras guardabas; vuelve a intentarlo"
        ) from exc


def _as_utc(value: datetime) -> datetime:
    """SQLite devuelve fechas sin zona; las guardamos siempre en UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
