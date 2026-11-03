"""Reparto de gastos del hogar: participantes, gastos, saldos y liquidaciones (ADR-0026, OF-1602).

Los gastos compartidos son del hogar y los ven todas las personas; no están enlazados a
movimientos de cuentas personales, así que no filtran nada de ellas (ADR-0013). Escribir exige
rol ``owner`` o ``editor``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from openfinance.application.errors import (
    ConflictError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
)
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import CategoryId
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import UserId
from openfinance.domain.sharing import (
    MAX_EVENTS,
    MAX_GUESTS,
    Balance,
    Event,
    EventSummary,
    Guest,
    Settlement,
    SettlementStatus,
    SharedExpense,
    SharingError,
    SplitMethod,
    Transfer,
    balances,
    split_amount,
    suggest_transfers,
    summarize_event,
)
from openfinance.domain.workspaces import Actor

REMOVED = "Persona que ya no está"


def require_writer(actor: Actor) -> None:
    if not actor.role.can_write:
        raise ForbiddenError("Tu rol en el hogar solo permite leer")


@dataclass(frozen=True, slots=True)
class Participant:
    id: UUID
    name: str
    is_guest: bool
    active: bool = True
    """Las personas que se fueron y los invitados archivados siguen en lo ya repartido."""


def _currency(uow: UnitOfWork, actor: Actor):  # type: ignore[no-untyped-def]
    household = uow.households.get(actor.household_id)
    if household is None:
        raise NotFoundError("Hogar no encontrado")
    return household.currency


def participants(uow: UnitOfWork, actor: Actor) -> list[Participant]:
    """Las personas del hogar y los invitados (activos y archivados)."""
    people = [
        Participant(u.id, u.display_name, False) for u in uow.households.members(actor.household_id)
    ]
    guests = [
        Participant(g.id, g.name, True, active=not g.archived)
        for g in uow.sharing.guests(actor.household_id)
    ]
    return [*people, *guests]


def _active_ids(uow: UnitOfWork, actor: Actor) -> set[UUID]:
    return {p.id for p in participants(uow, actor) if p.active}


def add_guest(uow: UnitOfWork, actor: Actor, name: str) -> Guest:
    require_writer(actor)
    if len([g for g in uow.sharing.guests(actor.household_id) if not g.archived]) >= MAX_GUESTS:
        raise ConflictError(f"Un hogar admite hasta {MAX_GUESTS} invitados")
    try:
        guest = Guest(uuid4(), actor.household_id, " ".join(name.split()))
    except SharingError as exc:
        raise InvalidRequestError(str(exc)) from exc
    uow.sharing.add_guest(guest)
    uow.commit()
    return guest


def archive_guest(uow: UnitOfWork, actor: Actor, guest_id: UUID) -> None:
    """Solo con saldo cero: un invitado que debe o al que deben no desaparece."""
    require_writer(actor)
    guest = uow.sharing.get_guest(actor.household_id, guest_id)
    if guest is None:
        raise NotFoundError("Invitado no encontrado")
    net = _balances(uow, actor).get(guest.id)
    if net is not None and not net.net.is_zero:
        raise InvalidRequestError("Solo se puede archivar a alguien con el saldo a cero")
    pending = [
        s
        for s in uow.sharing.settlements(actor.household_id)
        if s.status is SettlementStatus.PENDING and guest.id in (s.from_id, s.to_id)
    ]
    if pending:
        raise InvalidRequestError("Tiene liquidaciones pendientes: confírmalas o cancélalas antes")
    uow.sharing.save_guest(replace(guest, archived=True))
    uow.commit()


# --- gastos ----------------------------------------------------------------------------------


def _build_expense(
    uow: UnitOfWork,
    actor: Actor,
    expense_id: UUID,
    on: date,
    description: str,
    amount: str,
    payers: dict[UUID, str],
    method: SplitMethod,
    shares: dict[UUID, str],
    category_id: UUID | None,
    created_at: datetime,
    created_by: UserId,
    event_id: UUID | None = None,
) -> SharedExpense:
    currency = _currency(uow, actor)
    valid = _active_ids(uow, actor)
    try:
        total = Money.of(amount, currency)
        paid = {p: Money.of(v, currency) for p, v in payers.items()}
        values = {p: Decimal(v) for p, v in shares.items()}
    except (ValueError, ArithmeticError) as exc:
        raise InvalidRequestError(f"Importe no válido: {exc}") from exc
    if not set(payers) <= valid or not set(values) <= valid:
        raise InvalidRequestError("Hay personas que no están en el hogar")
    if (
        category_id is not None
        and uow.categories.get(actor.household_id, CategoryId(category_id)) is None
    ):
        raise NotFoundError("Categoría no encontrada")
    if event_id is not None:
        _open_event(uow, actor, event_id)
    try:
        who = list(values)  # el orden dado desempata los céntimos
        parts = split_amount(
            total,
            method,
            who,
            None if method is SplitMethod.EQUAL else values,
        )
        return SharedExpense(
            id=expense_id,
            household_id=actor.household_id,
            on=on,
            description=description,
            amount=total,
            payers=tuple(paid.items()),
            method=method,
            parts=tuple(parts.items()),
            created_by=created_by,
            created_at=created_at,
            category_id=category_id,
            event_id=event_id,
        )
    except SharingError as exc:
        raise InvalidRequestError(str(exc)) from exc


def preview_split(
    uow: UnitOfWork,
    actor: Actor,
    amount: str,
    method: SplitMethod,
    shares: dict[UUID, str],
) -> dict[UUID, Money]:
    """Cómo quedaría un reparto, sin guardar nada."""
    currency = _currency(uow, actor)
    try:
        total = Money.of(amount, currency)
        values = {p: Decimal(v) for p, v in shares.items()}
        return split_amount(
            total, method, list(values), None if method is SplitMethod.EQUAL else values
        )
    except (ValueError, ArithmeticError, SharingError) as exc:
        raise InvalidRequestError(str(exc)) from exc


def create_expense(
    uow: UnitOfWork,
    actor: Actor,
    on: date,
    description: str,
    amount: str,
    payers: dict[UUID, str],
    method: SplitMethod,
    shares: dict[UUID, str],
    category_id: UUID | None,
    now: datetime,
    event_id: UUID | None = None,
) -> SharedExpense:
    require_writer(actor)
    expense = _build_expense(
        uow, actor, uuid4(), on, description, amount, payers, method, shares, category_id, now,
        actor.user_id, event_id,
    )  # fmt: skip
    uow.sharing.add_expense(expense)
    uow.commit()
    return expense


def update_expense(
    uow: UnitOfWork,
    actor: Actor,
    expense_id: UUID,
    on: date,
    description: str,
    amount: str,
    payers: dict[UUID, str],
    method: SplitMethod,
    shares: dict[UUID, str],
    category_id: UUID | None,
    event_id: UUID | None = None,
) -> SharedExpense:
    """Corregir un gasto recalcula las partes. Uno anulado o de un evento cerrado no se corrige."""
    require_writer(actor)
    current = uow.sharing.get_expense(actor.household_id, expense_id)
    if current is None:
        raise NotFoundError("Gasto no encontrado")
    if current.voided:
        raise ConflictError("Ese gasto está anulado")
    _not_closed(uow, actor, current)
    expense = _build_expense(
        uow, actor, current.id, on, description, amount, payers, method, shares, category_id,
        current.created_at, current.created_by, event_id,
    )  # fmt: skip
    uow.sharing.save_expense(expense)
    uow.commit()
    return expense


def void_expense(uow: UnitOfWork, actor: Actor, expense_id: UUID) -> None:
    require_writer(actor)
    current = uow.sharing.get_expense(actor.household_id, expense_id)
    if current is None:
        raise NotFoundError("Gasto no encontrado")
    _not_closed(uow, actor, current)
    uow.sharing.save_expense(replace(current, voided=True))
    uow.commit()


def list_expenses(uow: UnitOfWork, actor: Actor) -> list[SharedExpense]:
    return [e for e in uow.sharing.expenses(actor.household_id) if not e.voided]


# --- saldos ----------------------------------------------------------------------------------


def _balances(uow: UnitOfWork, actor: Actor) -> dict[UUID, Balance]:
    currency = _currency(uow, actor)
    return balances(
        uow.sharing.expenses(actor.household_id),
        uow.sharing.settlements(actor.household_id),
        currency,
        [p.id for p in participants(uow, actor) if p.active],
    )


@dataclass(frozen=True, slots=True)
class BalanceView:
    balances: list[tuple[Participant, Balance]]
    suggestions: list[Transfer]


def balance_view(uow: UnitOfWork, actor: Actor) -> BalanceView:
    """El saldo entre personas (la suma es cero) y quién paga a quién."""
    currency = _currency(uow, actor)
    people = {p.id: p for p in participants(uow, actor)}
    result = _balances(uow, actor)
    rows = [
        (people.get(i) or Participant(i, REMOVED, False, active=False), b)
        for i, b in result.items()
    ]
    rows.sort(key=lambda r: (not r[0].active, r[0].name.casefold(), str(r[0].id)))
    suggestions = suggest_transfers({i: b.net for i, b in result.items()}, currency)
    return BalanceView(rows, suggestions)


# --- liquidaciones ---------------------------------------------------------------------------


def list_settlements(uow: UnitOfWork, actor: Actor) -> list[Settlement]:
    return uow.sharing.settlements(actor.household_id)


def create_settlement(
    uow: UnitOfWork,
    actor: Actor,
    from_id: UUID,
    to_id: UUID,
    amount: str,
    on: date,
    reference: str | None,
    now: datetime,
) -> tuple[Settlement, bool]:
    """Registra lo que alguien da a otra persona; queda pendiente hasta que se confirma.

    Quien la registra es quien paga, o cualquiera que edite si quien paga es un invitado.
    Repetir la misma referencia con los mismos datos devuelve la ya registrada (``False``).
    """
    require_writer(actor)
    valid = _active_ids(uow, actor)
    guests = {g.id for g in uow.sharing.guests(actor.household_id)}
    if from_id not in valid or to_id not in valid:
        raise InvalidRequestError("Hay personas que no están en el hogar")
    if from_id != actor.user_id and from_id not in guests:
        raise ForbiddenError("Solo puedes registrar lo que pagas tú (o lo de un invitado)")
    currency = _currency(uow, actor)
    try:
        new = Settlement(
            uuid4(), actor.household_id, from_id, to_id, Money.of(amount, currency), on,
            actor.user_id, now, reference=reference,
        )  # fmt: skip
    except (SharingError, ValueError, ArithmeticError) as exc:
        raise InvalidRequestError(str(exc)) from exc
    if reference is not None:
        existing = uow.sharing.settlement_by_reference(actor.household_id, reference)
        if existing is not None:
            same = (existing.from_id, existing.to_id, existing.amount, existing.on) == (
                new.from_id,
                new.to_id,
                new.amount,
                new.on,
            )
            if not same:
                raise ConflictError("Esa referencia ya se usó para otra liquidación")
            return existing, False
    uow.sharing.add_settlement(new)
    uow.commit()
    return new, True


def _pending(uow: UnitOfWork, actor: Actor, settlement_id: UUID) -> Settlement:
    settlement = uow.sharing.get_settlement(actor.household_id, settlement_id)
    if settlement is None:
        raise NotFoundError("Liquidación no encontrada")
    if settlement.status is not SettlementStatus.PENDING:
        raise ConflictError("Esa liquidación ya no está pendiente")
    return settlement


def confirm_settlement(
    uow: UnitOfWork, actor: Actor, settlement_id: UUID, now: datetime
) -> Settlement:
    """La confirma quien recibe; si recibe un invitado, cualquiera que edite. Solo entonces
    cambia los saldos."""
    require_writer(actor)
    settlement = _pending(uow, actor, settlement_id)
    receiver_is_guest = settlement.to_id in {g.id for g in uow.sharing.guests(actor.household_id)}
    if settlement.to_id != actor.user_id and not receiver_is_guest:
        raise ForbiddenError("La confirma quien recibe el dinero")
    confirmed = replace(
        settlement, status=SettlementStatus.CONFIRMED, confirmed_by=actor.user_id, confirmed_at=now
    )
    uow.sharing.save_settlement(confirmed)
    uow.commit()
    return confirmed


def cancel_settlement(uow: UnitOfWork, actor: Actor, settlement_id: UUID) -> Settlement:
    """La cancela quien la registró (o quien administra) mientras está pendiente."""
    require_writer(actor)
    settlement = _pending(uow, actor, settlement_id)
    if settlement.created_by != actor.user_id and not actor.role.can_manage:
        raise ForbiddenError("Solo quien la registró, o quien administra, puede cancelarla")
    cancelled = replace(settlement, status=SettlementStatus.CANCELLED)
    uow.sharing.save_settlement(cancelled)
    uow.commit()
    return cancelled


# --- eventos ---------------------------------------------------------------------------------


def _event(uow: UnitOfWork, actor: Actor, event_id: UUID) -> Event:
    event = uow.sharing.get_event(actor.household_id, event_id)
    if event is None:
        raise NotFoundError("Evento no encontrado")
    return event


def _open_event(uow: UnitOfWork, actor: Actor, event_id: UUID) -> Event:
    event = _event(uow, actor, event_id)
    if event.closed:
        raise ConflictError("Ese evento está cerrado: ábrelo de nuevo para añadir gastos")
    return event


def _not_closed(uow: UnitOfWork, actor: Actor, expense: SharedExpense) -> None:
    if expense.event_id is not None and _event(uow, actor, expense.event_id).closed:
        raise ConflictError("El evento de este gasto está cerrado: ábrelo para cambiarlo")


def list_events(uow: UnitOfWork, actor: Actor) -> list[Event]:
    return uow.sharing.events(actor.household_id)


def create_event(
    uow: UnitOfWork,
    actor: Actor,
    name: str,
    icon: str,
    starts_on: date | None,
    ends_on: date | None,
    now: datetime,
) -> Event:
    require_writer(actor)
    if len(uow.sharing.events(actor.household_id)) >= MAX_EVENTS:
        raise ConflictError(f"Un hogar admite hasta {MAX_EVENTS} eventos")
    try:
        event = Event(
            uuid4(),
            actor.household_id,
            " ".join(name.split()),
            now,
            icon.strip(),
            starts_on,
            ends_on,
        )
    except SharingError as exc:
        raise InvalidRequestError(str(exc)) from exc
    uow.sharing.add_event(event)
    uow.commit()
    return event


def update_event(
    uow: UnitOfWork,
    actor: Actor,
    event_id: UUID,
    name: str,
    icon: str,
    starts_on: date | None,
    ends_on: date | None,
) -> Event:
    require_writer(actor)
    current = _event(uow, actor, event_id)
    try:
        event = replace(
            current,
            name=" ".join(name.split()),
            icon=icon.strip(),
            starts_on=starts_on,
            ends_on=ends_on,
        )
    except SharingError as exc:
        raise InvalidRequestError(str(exc)) from exc
    uow.sharing.save_event(event)
    uow.commit()
    return event


def set_event_closed(uow: UnitOfWork, actor: Actor, event_id: UUID, closed: bool) -> Event:
    require_writer(actor)
    event = replace(_event(uow, actor, event_id), closed=closed)
    uow.sharing.save_event(event)
    uow.commit()
    return event


def delete_event(uow: UnitOfWork, actor: Actor, event_id: UUID) -> None:
    """Solo un evento sin gastos (ni anulados): con gastos se cierra, no se borra."""
    require_writer(actor)
    event = _event(uow, actor, event_id)
    if uow.sharing.event_expense_count(actor.household_id, event.id) > 0:
        raise ConflictError("Un evento con gastos no se borra: ciérralo")
    uow.sharing.delete_event(actor.household_id, event.id)
    uow.commit()


@dataclass(frozen=True, slots=True)
class EventView:
    event: Event
    summary: EventSummary
    expenses: list[SharedExpense]
    participants: list[Participant]
    """Quienes aparecen en sus gastos (también si ya no están)."""
    category_names: dict[UUID, str]
    suggestions: list[Transfer]


def event_view(uow: UnitOfWork, actor: Actor, event_id: UUID) -> EventView:
    """El resumen de un evento: total, lo pagado y la parte de cada uno, saldos y categorías.

    Los saldos son solo con los gastos del evento, sin liquidaciones: dicen cómo quedaría
    saldarlo por separado.
    """
    event = _event(uow, actor, event_id)
    currency = _currency(uow, actor)
    expenses = [e for e in uow.sharing.expenses(actor.household_id) if e.event_id == event.id]
    summary = summarize_event(expenses, currency)
    known = {p.id: p for p in participants(uow, actor)}
    seen = list(summary.balances)
    people = [known.get(i) or Participant(i, REMOVED, False, active=False) for i in seen]
    people.sort(key=lambda p: (not p.active, p.name.casefold(), str(p.id)))
    names = {c.id: c.name for c in uow.categories.for_household(actor.household_id)}
    nets = {i: b.net for i, b in summary.balances.items()}
    return EventView(
        event,
        summary,
        [e for e in expenses if not e.voided],
        people,
        {k: v for k, v in names.items() if k in summary.by_category},
        suggest_transfers(nets, currency),
    )
