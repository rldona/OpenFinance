"""Reparto de gastos entre las personas del hogar y sus invitados (ADR-0026, OF-1602).

Todo el cálculo es en unidades menores enteras (céntimos): las partes de un gasto suman
**exactamente** su importe y los saldos entre personas suman **exactamente** cero. Lo que sobra
al repartir se asigna por mayor resto, con desempate determinista por el orden dado.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from uuid import UUID

from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import UserId, WorkspaceId

MAX_PARTICIPANTS = 30
MAX_DESCRIPTION = 200
MAX_NAME = 60
MAX_GUESTS = 30
MAX_REFERENCE = 64
HUNDRED = Decimal(100)


class SharingError(ValueError):
    pass


class SplitMethod(StrEnum):
    EQUAL = "equal"
    PERCENTAGE = "percentage"
    EXACT = "exact"
    SHARES = "shares"


def to_minor(money: Money) -> int:
    return int(money.amount.scaleb(money.currency.minor_units))


def from_minor(minor: int, currency: Currency) -> Money:
    return Money.of(Decimal(minor).scaleb(-currency.minor_units), currency)


def _weighted(total: int, weights: Sequence[Fraction]) -> list[int]:
    """Reparte ``total`` en proporción a ``weights`` por mayor resto; la suma es ``total``."""
    whole = sum(weights, Fraction(0))
    if whole <= 0:
        raise SharingError("El reparto necesita pesos mayores que cero")
    exact = [total * w / whole for w in weights]
    parts = [int(e) for e in exact]  # suelo: todos los pesos son positivos
    left = total - sum(parts)
    by_remainder = sorted(range(len(parts)), key=lambda i: (-(exact[i] - parts[i]), i))
    for i in by_remainder[:left]:
        parts[i] += 1
    return parts


def split_amount(
    total: Money,
    method: SplitMethod,
    participants: Sequence[UUID],
    values: Mapping[UUID, Decimal] | None = None,
) -> dict[UUID, Money]:
    """La parte de cada participante. Rechaza lo que no cuadra en vez de ajustarlo en silencio.

    ``values`` son los porcentajes, los importes exactos o los pesos, según el método; en
    ``equal`` no se usan. El orden de ``participants`` desempata el reparto de los céntimos.
    """
    ids = list(participants)
    if not ids or len(ids) > MAX_PARTICIPANTS:
        raise SharingError(f"Un gasto se reparte entre 1 y {MAX_PARTICIPANTS} personas")
    if len(set(ids)) != len(ids):
        raise SharingError("Hay participantes repetidos")
    if total.amount <= 0:
        raise SharingError("El gasto debe ser mayor que cero")
    minor = to_minor(total)
    given = dict(values or {})
    if method is not SplitMethod.EQUAL and set(given) != set(ids):
        raise SharingError("Hay que indicar el valor de cada participante, y solo de ellos")
    if method is SplitMethod.EQUAL:
        parts = _weighted(minor, [Fraction(1)] * len(ids))
    elif method is SplitMethod.SHARES:
        if any(v <= 0 for v in given.values()):
            raise SharingError("Los pesos deben ser mayores que cero")
        parts = _weighted(minor, [Fraction(given[i]) for i in ids])
    elif method is SplitMethod.PERCENTAGE:
        if any(v < 0 for v in given.values()):
            raise SharingError("Los porcentajes no pueden ser negativos")
        if sum(given.values(), Decimal(0)) != HUNDRED:
            raise SharingError("Los porcentajes deben sumar exactamente 100")
        parts = _weighted(minor, [Fraction(given[i]) for i in ids])
    else:
        exact = [Money.of(given[i], total.currency) for i in ids]
        if any(m.amount < 0 for m in exact):
            raise SharingError("Los importes no pueden ser negativos")
        parts = [to_minor(m) for m in exact]
        if sum(parts) != minor:
            raise SharingError("Los importes deben sumar exactamente el total del gasto")
    return {i: from_minor(p, total.currency) for i, p in zip(ids, parts, strict=True)}


def _sum(values: Iterable[Money], currency: Currency) -> Money:
    total = Money.zero(currency)
    for v in values:
        total = total + v
    return total


@dataclass(frozen=True, slots=True)
class SharedExpense:
    id: UUID
    household_id: WorkspaceId
    on: date
    description: str
    amount: Money
    payers: tuple[tuple[UUID, Money], ...]
    """Quién pagó y cuánto: la suma es exactamente el importe."""
    method: SplitMethod
    parts: tuple[tuple[UUID, Money], ...]
    """Lo que le toca a cada participante: la suma es exactamente el importe."""
    created_by: UserId
    created_at: datetime
    category_id: UUID | None = None
    event_id: UUID | None = None
    voided: bool = False

    def __post_init__(self) -> None:
        currency = self.amount.currency
        if self.amount.amount <= 0:
            raise SharingError("El gasto debe ser mayor que cero")
        text = self.description.strip()
        if not text or len(text) > MAX_DESCRIPTION or not text.isprintable():
            raise SharingError(f"El concepto va de 1 a {MAX_DESCRIPTION} caracteres")
        for name, group in (("pagadores", self.payers), ("partes", self.parts)):
            ids = [p for p, _ in group]
            if not ids or len(set(ids)) != len(ids):
                raise SharingError(f"Los {name} no pueden estar vacíos ni repetirse")
            if any(m.amount < 0 or m.currency != currency for _, m in group):
                raise SharingError("Los importes no pueden ser negativos ni de otra moneda")
            if _sum((m for _, m in group), currency) != self.amount:
                raise SharingError(f"Los {name} deben sumar exactamente el importe del gasto")

    def paid(self, who: UUID) -> Money:
        return next((m for p, m in self.payers if p == who), Money.zero(self.amount.currency))

    def share(self, who: UUID) -> Money:
        return next((m for p, m in self.parts if p == who), Money.zero(self.amount.currency))


class SettlementStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Settlement:
    """Quien debe da dinero a quien le corresponde. Solo cuenta cuando se confirma."""

    id: UUID
    household_id: WorkspaceId
    from_id: UUID
    to_id: UUID
    amount: Money
    on: date
    created_by: UserId
    created_at: datetime
    status: SettlementStatus = SettlementStatus.PENDING
    reference: str | None = None
    """Para que registrar lo mismo dos veces no lo duplique."""
    confirmed_by: UserId | None = None
    confirmed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.from_id == self.to_id:
            raise SharingError("Una liquidación es entre dos personas distintas")
        if self.amount.amount <= 0:
            raise SharingError("La liquidación debe ser mayor que cero")
        if self.reference is not None and not 1 <= len(self.reference) <= MAX_REFERENCE:
            raise SharingError(f"La referencia va de 1 a {MAX_REFERENCE} caracteres")


@dataclass(frozen=True, slots=True)
class Guest:
    """Una persona del grupo sin usuario: no tiene acceso a nada; quien edita anota por ella."""

    id: UUID
    household_id: WorkspaceId
    name: str
    archived: bool = False

    def __post_init__(self) -> None:
        text = self.name.strip()
        if not text or len(text) > MAX_NAME or not text.isprintable():
            raise SharingError(f"El nombre va de 1 a {MAX_NAME} caracteres")


@dataclass(frozen=True, slots=True)
class Balance:
    participant: UUID
    paid: Money
    share: Money
    settled: Money
    """Liquidaciones confirmadas: lo enviado menos lo recibido."""

    @property
    def net(self) -> Money:
        """Positivo: le deben. Negativo: debe."""
        return self.paid - self.share + self.settled


def balances(
    expenses: Iterable[SharedExpense],
    settlements: Iterable[Settlement],
    currency: Currency,
    participants: Iterable[UUID] = (),
) -> dict[UUID, Balance]:
    """El saldo entre personas. La suma de todos los saldos es exactamente cero."""
    zero = Money.zero(currency)
    paid: dict[UUID, Money] = {p: zero for p in participants}
    share: dict[UUID, Money] = dict(paid)
    settled: dict[UUID, Money] = dict(paid)
    for e in expenses:
        if e.voided:
            continue
        for who, amount in e.payers:
            paid[who] = paid.get(who, zero) + amount
            share.setdefault(who, zero)
            settled.setdefault(who, zero)
        for who, amount in e.parts:
            share[who] = share.get(who, zero) + amount
            paid.setdefault(who, zero)
            settled.setdefault(who, zero)
    for s in settlements:
        if s.status is not SettlementStatus.CONFIRMED:
            continue
        for who in (s.from_id, s.to_id):
            paid.setdefault(who, zero)
            share.setdefault(who, zero)
            settled.setdefault(who, zero)
        settled[s.from_id] = settled[s.from_id] + s.amount
        settled[s.to_id] = settled[s.to_id] - s.amount
    return {p: Balance(p, paid[p], share[p], settled[p]) for p in paid}


@dataclass(frozen=True, slots=True)
class Transfer:
    from_id: UUID
    to_id: UUID
    amount: Money


def suggest_transfers(nets: Mapping[UUID, Money], currency: Currency) -> list[Transfer]:
    """Quién paga a quién con el mínimo de transferencias.

    Empareja al que más debe con al que más le deben, y repite: cada transferencia salda al
    menos a una de las dos personas, así que hay como mucho una menos que personas implicadas.
    """
    debtors = sorted(
        ((p, -to_minor(m)) for p, m in nets.items() if m.amount < 0),
        key=lambda x: (-x[1], str(x[0])),
    )
    creditors = sorted(
        ((p, to_minor(m)) for p, m in nets.items() if m.amount > 0),
        key=lambda x: (-x[1], str(x[0])),
    )
    out: list[Transfer] = []
    d = c = 0
    owed = [x[1] for x in debtors]
    due = [x[1] for x in creditors]
    while d < len(debtors) and c < len(creditors):
        amount = min(owed[d], due[c])
        if amount > 0:
            out.append(Transfer(debtors[d][0], creditors[c][0], from_minor(amount, currency)))
        owed[d] -= amount
        due[c] -= amount
        if owed[d] == 0:
            d += 1
        if due[c] == 0:
            c += 1
    return out
