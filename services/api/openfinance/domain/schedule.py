"""Pagos programados: calendario de ocurrencias y emparejado con lo cobrado (ADR-0021, OF-1201).

Todo es función pura de las fechas: no hay reloj ni tareas programadas. Una ocurrencia es una
fecha **esperada**, nunca un movimiento: la previsión no escribe en el libro.
"""

from __future__ import annotations

import calendar
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, NewType
from uuid import UUID

from openfinance.domain.categories import CategoryId
from openfinance.domain.ledger import Transaction
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId, WorkspaceId

ScheduleId = NewType("ScheduleId", UUID)

MAX_NAME = 60
MAX_INTERVAL = 60
MATCH_DAYS = 7
"""Un cobro cuenta para una fecha esperada si cae como mucho a una semana de ella."""
MATCH_TOLERANCE = Decimal("0.05")
"""…y su importe difiere como mucho un 5 % (salvo en los pagos de importe variable)."""
LATE_WINDOW_DAYS = 45
"""Solo se avisa de atrasos recientes: un pago de hace un año sin cobro ya no es noticia."""
MAX_OCCURRENCES = 1000


class ScheduleError(ValueError):
    pass


class Frequency(StrEnum):
    ONCE = "once"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class OccurrenceStatus(StrEnum):
    PAID = "paid"
    """Hay un cobro que lo cumple."""
    PENDING = "pending"
    LATE = "late"
    """Pasó la fecha y no ha llegado nada: se avisa y no se suma a la previsión."""


@dataclass(frozen=True, slots=True)
class ScheduledPayment:
    id: ScheduleId
    household_id: WorkspaceId
    name: str
    amount: Money
    """Con signo: negativo es un pago, positivo es un ingreso."""
    account_id: AccountId
    frequency: Frequency
    first_due: date
    """La primera fecha esperada; el día del mes se toma de aquí."""
    interval: int = 1
    """Cada cuántas semanas, meses o años."""
    ends_on: date | None = None
    category_id: CategoryId | None = None
    merchant: str = ""
    variable: bool = False
    """Importe variable (luz, agua): se empareja con cualquier importe del mismo signo."""
    active: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > MAX_NAME:
            raise ScheduleError(f"El pago necesita un nombre de hasta {MAX_NAME} caracteres")
        if self.amount.is_zero:
            raise ScheduleError("El importe no puede ser cero")
        if not 1 <= self.interval <= MAX_INTERVAL:
            raise ScheduleError(f"La repetición va de 1 a {MAX_INTERVAL}")
        if self.frequency is Frequency.ONCE and self.interval != 1:
            raise ScheduleError("Un pago único no se repite")
        if self.ends_on is not None and self.ends_on < self.first_due:
            raise ScheduleError("El fin no puede ser anterior al primer cobro")
        if len(self.merchant) > 120:
            raise ScheduleError("Comercio demasiado largo")

    @property
    def is_income(self) -> bool:
        return self.amount.amount > 0

    def definition(self) -> str:
        """El texto canónico (registro de cambios y base de datos)."""
        return json.dumps(
            {
                "name": self.name,
                "amount": str(self.amount.amount),
                "currency": self.amount.currency.code,
                "account_id": str(self.account_id),
                "frequency": self.frequency.value,
                "interval": self.interval,
                "first_due": self.first_due.isoformat(),
                "ends_on": self.ends_on.isoformat() if self.ends_on else None,
                "category_id": str(self.category_id) if self.category_id else None,
                "merchant": self.merchant,
                "variable": self.variable,
                "active": self.active,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )


def from_definition(
    schedule_id: UUID, household_id: WorkspaceId, definition: str
) -> ScheduledPayment:
    data: dict[str, Any] = json.loads(definition)
    return ScheduledPayment(
        id=ScheduleId(schedule_id),
        household_id=household_id,
        name=data["name"],
        amount=Money.of(data["amount"], data["currency"]),
        account_id=AccountId(UUID(data["account_id"])),
        frequency=Frequency(data["frequency"]),
        first_due=date.fromisoformat(data["first_due"]),
        interval=int(data["interval"]),
        ends_on=date.fromisoformat(data["ends_on"]) if data["ends_on"] else None,
        category_id=CategoryId(UUID(data["category_id"])) if data["category_id"] else None,
        merchant=data["merchant"],
        variable=bool(data["variable"]),
        active=bool(data["active"]),
    )


def _add_months(anchor: date, months: int) -> date:
    """``anchor`` más ``months`` meses, recortando al último día del mes si hace falta
    (el 31 de enero más un mes es el 28 o 29 de febrero, y el siguiente vuelve al 31)."""
    index = anchor.year * 12 + anchor.month - 1 + months
    year, month = index // 12, index % 12 + 1
    if year > 9998:
        raise OverflowError
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def _nth(payment: ScheduledPayment, k: int) -> date:
    if payment.frequency is Frequency.WEEKLY:
        return payment.first_due + timedelta(days=7 * payment.interval * k)
    if payment.frequency is Frequency.MONTHLY:
        return _add_months(payment.first_due, payment.interval * k)
    if payment.frequency is Frequency.YEARLY:
        return _add_months(payment.first_due, 12 * payment.interval * k)
    return payment.first_due


def occurrences(payment: ScheduledPayment, start: date, end: date) -> list[date]:
    """Las fechas esperadas de ``start`` a ``end`` (ambas incluidas), en orden.

    Se calcula siempre desde la primera fecha (no se encadena de una en otra), así que el día
    del mes no se va desplazando tras un mes corto.
    """
    last = min(end, payment.ends_on) if payment.ends_on else end
    if last < start or last < payment.first_due:
        return []
    if payment.frequency is Frequency.ONCE:
        return [payment.first_due] if start <= payment.first_due <= last else []
    first = max(start, payment.first_due)
    days = (first - payment.first_due).days
    if payment.frequency is Frequency.WEEKLY:
        k = days // (7 * payment.interval)
    else:  # una cota inferior holgada; el bucle avanza hasta ``start``
        unit = payment.interval * (12 if payment.frequency is Frequency.YEARLY else 1)
        k = max(0, days // (31 * unit) - 1)
    found: list[date] = []
    try:
        for step in range(k, k + MAX_OCCURRENCES + 1):
            due = _nth(payment, step)
            if due > last:
                break
            if due >= start:
                found.append(due)
            if len(found) >= MAX_OCCURRENCES:
                break
    except OverflowError:
        pass
    return found


@dataclass(frozen=True, slots=True)
class Occurrence:
    payment_id: ScheduleId
    due: date
    amount: Money
    status: OccurrenceStatus
    transaction_id: TransactionId | None = None
    """El cobro que la cumple, si lo hay."""


def _fits(payment: ScheduledPayment, t: Transaction, due: date) -> bool:
    if t.voided or t.account_id != payment.account_id:
        return False
    if t.amount.currency != payment.amount.currency:
        return False
    if (t.amount.amount > 0) != payment.is_income:
        return False
    if abs((t.booked_at.date() - due).days) > MATCH_DAYS:
        return False
    if payment.variable:
        return True
    expected = abs(payment.amount.amount)
    return abs(abs(t.amount.amount) - expected) <= expected * MATCH_TOLERANCE


def match(
    payment: ScheduledPayment, dues: Sequence[date], transactions: Iterable[Transaction]
) -> dict[date, TransactionId]:
    """Qué cobro cumple cada fecha. Cada cobro cumple como mucho una fecha; entre varios
    candidatos gana el más cercano en fecha y, a igualdad, en importe."""
    pool = [t for t in transactions if not t.voided and t.account_id == payment.account_id]
    used: set[TransactionId] = set()
    matched: dict[date, TransactionId] = {}
    expected = abs(payment.amount.amount)
    for due in sorted(dues):
        candidates = [t for t in pool if t.id not in used and _fits(payment, t, due)]
        if not candidates:
            continue
        best = min(
            candidates,
            key=lambda t: (
                abs((t.booked_at.date() - due).days),
                abs(abs(t.amount.amount) - expected),
                t.booked_at,
                str(t.id),
            ),
        )
        used.add(best.id)
        matched[due] = best.id
    return matched


def upcoming(
    payment: ScheduledPayment,
    transactions: Iterable[Transaction],
    today: date,
    until: date,
) -> list[Occurrence]:
    """Las ocurrencias recientes y futuras (hasta ``until``) con su estado.

    Empieza ``LATE_WINDOW_DAYS`` antes de hoy: más atrás ya no se avisa. Un pago desactivado no
    tiene ocurrencias.
    """
    if not payment.active:
        return []
    start = today - timedelta(days=LATE_WINDOW_DAYS)
    dues = occurrences(payment, start, until)
    paid = match(payment, dues, transactions)
    out: list[Occurrence] = []
    for due in dues:
        tid = paid.get(due)
        if tid is not None:
            status = OccurrenceStatus.PAID
        elif due < today:
            status = OccurrenceStatus.LATE
        else:
            status = OccurrenceStatus.PENDING
        out.append(Occurrence(payment.id, due, payment.amount, status, tid))
    return out
