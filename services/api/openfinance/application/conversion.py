"""Varias monedas: tipos de cambio manuales y conversión para los informes (ADR-0019, OF-1008).

Cada cuenta va en su moneda; los informes se calculan en la del hogar. Un movimiento en otra
moneda sin tipo de cambio para su fecha **no entra** en el informe y se cuenta aparte, para
decirlo («3 movimientos en USD sin tipo de cambio») en lugar de inventar un valor.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from openfinance.application import changes as change_log
from openfinance.application.errors import InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.changes import Change, Entity
from openfinance.domain.ledger import Transaction
from openfinance.domain.rates import (
    RATE_DECIMALS,
    Converter,
    ExchangeRate,
    RateError,
    check_foreign,
)
from openfinance.domain.shared import Currency
from openfinance.domain.shared.ids import AccountId, WorkspaceId
from openfinance.domain.workspaces import Actor

_RATE_QUANTUM = Decimal(1).scaleb(-RATE_DECIMALS)
_EPOCH = datetime(1900, 1, 1)  # noqa: DTZ001 - hora local del banco, sin zona
_FAR_FUTURE = datetime(9000, 1, 1)  # noqa: DTZ001


def rate_entity_id(currency: Currency, on: date) -> str:
    return f"{currency.code}|{on.isoformat()}"


def _reference(uow: UnitOfWork, household_id: WorkspaceId) -> Currency:
    household = uow.households.get(household_id)
    if household is None:
        raise NotFoundError("Hogar no encontrado")
    return household.currency


def converter(uow: UnitOfWork, household_id: WorkspaceId) -> Converter:
    return Converter.of(_reference(uow, household_id), uow.rates.all(household_id))


def report_transactions(
    uow: UnitOfWork,
    household_id: WorkspaceId,
    accounts: list[AccountId],
    start: datetime,
    end: datetime,
) -> list[Transaction]:
    """Los movimientos de un informe, todos en la moneda del hogar. Los de otra moneda sin
    tipo de cambio para su fecha se dejan fuera (``missing_rates`` los cuenta)."""
    txns = uow.transactions.in_range(household_id, accounts, start, end)
    reference = _reference(uow, household_id)
    if all(t.amount.currency == reference for t in txns):
        return txns  # un hogar de una sola moneda no nota nada
    conv = converter(uow, household_id)
    out: list[Transaction] = []
    for t in txns:
        money = conv.convert(t.amount, t.booked_at.date())
        if money is not None:
            out.append(t if money == t.amount else replace(t, amount=money))
    return out


@dataclass(frozen=True, slots=True)
class MissingRate:
    currency: str
    count: int
    """Movimientos en esa moneda que no entran en los informes."""
    first: date
    """Fecha del más antiguo: el tipo tiene que ser de ese día o anterior."""


def missing_rates(uow: UnitOfWork, actor: Actor) -> list[MissingRate]:
    """Qué monedas necesitan un tipo de cambio para que sus movimientos entren en los informes."""
    reference = _reference(uow, actor.household_id)
    foreign = [a.id for a in visible_accounts(uow, actor) if a.currency != reference]
    if not foreign:
        return []
    conv = converter(uow, actor.household_id)
    counts: dict[str, list[date]] = {}
    for t in uow.transactions.in_range(actor.household_id, foreign, _EPOCH, _FAR_FUTURE):
        if conv.convert(t.amount, t.booked_at.date()) is None:
            counts.setdefault(t.amount.currency.code, []).append(t.booked_at.date())
    return [MissingRate(c, len(d), min(d)) for c, d in sorted(counts.items())]


def list_rates(uow: UnitOfWork, actor: Actor) -> list[ExchangeRate]:
    return uow.rates.all(actor.household_id)


def set_rate(
    uow: UnitOfWork,
    actor: Actor,
    currency_code: str,
    on: date,
    rate_text: str,
    now: datetime,
    today: date,
) -> tuple[ExchangeRate, UUID | None]:
    """Pone (o corrige) el tipo de cambio de una moneda en una fecha; se puede deshacer."""
    reference = _reference(uow, actor.household_id)
    try:
        currency = Currency(currency_code.strip().upper())
        check_foreign(reference, currency)
        rate = ExchangeRate(
            actor.household_id, currency, on, Decimal(rate_text.strip().replace(",", "."))
        )
    except (ValueError, InvalidOperation, RateError) as exc:
        raise InvalidRequestError(str(exc)) from exc
    # A la escala de la base de datos: el valor del registro de cambios es siempre el mismo texto.
    rate = replace(rate, rate=rate.rate.quantize(_RATE_QUANTUM))
    if on > today:
        raise InvalidRequestError("El tipo de cambio no puede ser de una fecha futura")
    before = uow.rates.get(actor.household_id, currency, on)
    if before is not None and before.rate == rate.rate:
        return rate, None
    uow.rates.upsert(rate, actor.user_id)
    operation = change_log.record(
        uow,
        actor,
        "rate.set",
        f"Tipo de cambio {currency} a {on.isoformat()}: {rate.rate.normalize():f}",
        [
            Change(
                Entity.RATE,
                rate_entity_id(currency, on),
                "rate",
                f"{before.rate:f}" if before else None,
                f"{rate.rate:f}",
            )
        ],
        now,
    )
    uow.commit()
    return rate, operation.id if operation else None


def delete_rate(
    uow: UnitOfWork, actor: Actor, currency_code: str, on: date, now: datetime
) -> UUID | None:
    try:
        currency = Currency(currency_code.strip().upper())
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    before = uow.rates.get(actor.household_id, currency, on)
    if before is None:
        raise NotFoundError("Tipo de cambio no encontrado")
    uow.rates.delete(actor.household_id, currency, on)
    operation = change_log.record(
        uow,
        actor,
        "rate.delete",
        f"Tipo de cambio {currency} a {on.isoformat()} borrado",
        [Change(Entity.RATE, rate_entity_id(currency, on), "rate", f"{before.rate:f}", None)],
        now,
    )
    uow.commit()
    return operation.id if operation else None
