from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from openfinance.domain.ledger import TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.text import normalize_text


@dataclass(frozen=True, slots=True)
class ImportedRow:
    """Una fila de un extracto ya normalizada, antes de guardarse como movimiento."""

    booked_at: datetime
    value_date: date
    description: str
    amount: Money
    """Efecto total en la cuenta, comisiones incluidas."""
    bank_type: str
    """Tipo según el banco (p. ej. ``CARD_PAYMENT``); se conserva como procedencia."""
    suggested_kind: TransactionKind
    fingerprint: str
    member: str | None = None
    """Persona que aporta, si ``suggested_kind`` es ``CONTRIBUTION``."""
    balance_after: Money | None = None
    line: int = 0


@dataclass(frozen=True, slots=True)
class SkippedRow:
    line: int
    reason: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class BalanceMismatch:
    line: int
    expected: Money
    reported: Money


@dataclass(slots=True)
class ParseResult:
    rows: list[ImportedRow] = field(default_factory=list)
    """En el orden en que el banco las aplica al saldo: de la más antigua a la más reciente."""
    skipped: list[SkippedRow] = field(default_factory=list)
    balance_mismatches: list[BalanceMismatch] = field(default_factory=list)

    @property
    def closing_balance(self) -> Money | None:
        """Saldo que informa el banco tras la última fila aplicada."""
        return next(
            (r.balance_after for r in reversed(self.rows) if r.balance_after is not None), None
        )


def fingerprint(
    account_key: str,
    booked_at: datetime,
    amount: Money,
    description: str,
    occurrence: int = 0,
    *,
    discriminator: str = "",
) -> str:
    """Huella estable para deduplicar filas sin identificador del banco.

    ``occurrence`` distingue filas idénticas dentro del mismo extracto (dos cafés iguales
    en el mismo segundo), de forma que no se fusionen entre sí.

    ``discriminator`` añade un dato propio de la fila cuando el banco no da hora (p. ej. el
    saldo tras el movimiento). Vacío, la huella es la de siempre: las ya guardadas no cambian.
    """
    parts = [
        account_key,
        booked_at.isoformat(timespec="seconds"),
        str(amount.amount),
        amount.currency.code,
        normalize_text(description),
        str(occurrence),
    ]
    if discriminator:
        parts.append(discriminator)
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode()).hexdigest()


def check_running_balance(rows: Sequence[ImportedRow]) -> list[BalanceMismatch]:
    """Comprueba que saldo anterior + importe = saldo informado por el banco.

    Un descuadre suele indicar filas que faltan en el extracto.
    """
    mismatches: list[BalanceMismatch] = []
    previous: Money | None = None
    for row in rows:
        if row.balance_after is None:
            previous = None
            continue
        if previous is not None:
            expected = previous + row.amount
            if expected != row.balance_after:
                mismatches.append(BalanceMismatch(row.line, expected, row.balance_after))
        previous = row.balance_after
    return mismatches
