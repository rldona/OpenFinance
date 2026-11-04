"""Pagos programados: crear, cambiar, borrar y ver lo que viene (ADR-0021, OF-1201).

Un pago programado cuelga de una cuenta y hereda su visibilidad (ADR-0013): quien no ve la cuenta
no ve el pago, ni su calendario, ni lo puede cambiar ni deshacer. Las ocurrencias se calculan en
cada consulta; nada se escribe en el libro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from openfinance.application import changes as change_log
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import CategoryId
from openfinance.domain.changes import Change, Entity
from openfinance.domain.ledger import Account, Transaction
from openfinance.domain.schedule import (
    LATE_WINDOW_DAYS,
    MATCH_DAYS,
    Frequency,
    Occurrence,
    ScheduledPayment,
    ScheduleError,
    ScheduleId,
    upcoming,
)
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId
from openfinance.domain.workspaces import Actor

MAX_PAYMENTS = 200
MAX_HORIZON_DAYS = 400
DEFAULT_HORIZON_DAYS = 60


@dataclass(frozen=True, slots=True)
class PaymentDraft:
    name: str
    amount: str
    account_id: UUID
    frequency: Frequency
    first_due: date
    interval: int = 1
    ends_on: date | None = None
    category_id: UUID | None = None
    merchant: str = ""
    variable: bool = False
    active: bool = True


@dataclass(frozen=True, slots=True)
class PaymentView:
    payment: ScheduledPayment
    occurrences: list[Occurrence]


def visible_payments(uow: UnitOfWork, actor: Actor) -> list[ScheduledPayment]:
    visible = {a.id for a in visible_accounts(uow, actor)}
    return [p for p in uow.schedule.for_household(actor.household_id) if p.account_id in visible]


def _account(uow: UnitOfWork, actor: Actor, account_id: UUID) -> Account:
    account = next((a for a in visible_accounts(uow, actor) if a.id == account_id), None)
    if account is None:
        raise NotFoundError("Cuenta no encontrada")
    return account


def _own(uow: UnitOfWork, actor: Actor, schedule_id: UUID) -> ScheduledPayment:
    payment = uow.schedule.get(actor.household_id, schedule_id)
    if payment is None or payment.account_id not in {a.id for a in visible_accounts(uow, actor)}:
        raise NotFoundError("Pago no encontrado")
    return payment


def _build(
    uow: UnitOfWork, actor: Actor, draft: PaymentDraft, schedule_id: UUID
) -> ScheduledPayment:
    account = _account(uow, actor, draft.account_id)
    try:
        amount = Money.of(Decimal(draft.amount.strip().replace(",", ".")), account.currency)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidRequestError("Importe no válido") from exc
    category_id = None
    if draft.category_id is not None:
        category = uow.categories.get(actor.household_id, CategoryId(draft.category_id))
        if category is None:
            raise NotFoundError("Categoría no encontrada")
        if category.hidden:
            raise InvalidRequestError(f"La categoría «{category.name}» está oculta")
        category_id = category.id
    try:
        return ScheduledPayment(
            id=ScheduleId(schedule_id),
            household_id=actor.household_id,
            name=" ".join(draft.name.split()),
            amount=amount,
            account_id=account.id,
            frequency=draft.frequency,
            first_due=draft.first_due,
            interval=draft.interval,
            ends_on=draft.ends_on,
            category_id=category_id,
            merchant=" ".join(draft.merchant.split()),
            variable=draft.variable,
            active=draft.active,
        )
    except ScheduleError as exc:
        raise InvalidRequestError(str(exc)) from exc


def _check_name(uow: UnitOfWork, actor: Actor, name: str, own_id: UUID | None) -> None:
    wanted = " ".join(name.split()).casefold()
    if any(p.name.casefold() == wanted and p.id != own_id for p in visible_payments(uow, actor)):
        raise ConflictError("Ya hay un pago con ese nombre")


def create_payment(
    uow: UnitOfWork, actor: Actor, draft: PaymentDraft, now: datetime
) -> tuple[ScheduledPayment, UUID | None]:
    if len(uow.schedule.for_household(actor.household_id)) >= MAX_PAYMENTS:
        raise ConflictError(f"El hogar ya tiene {MAX_PAYMENTS} pagos programados")
    _check_name(uow, actor, draft.name, None)
    payment = _build(uow, actor, draft, uuid4())
    uow.schedule.save(payment, actor.user_id)
    operation = change_log.record(
        uow,
        actor,
        "schedule.create",
        f"Pago programado «{payment.name}» creado",
        [Change(Entity.SCHEDULE, str(payment.id), "definition", None, payment.definition())],
        now,
    )
    uow.commit()
    return payment, operation.id if operation else None


def update_payment(
    uow: UnitOfWork, actor: Actor, schedule_id: UUID, draft: PaymentDraft, now: datetime
) -> tuple[ScheduledPayment, UUID | None]:
    before = _own(uow, actor, schedule_id)
    _check_name(uow, actor, draft.name, schedule_id)
    updated = _build(uow, actor, draft, schedule_id)
    if updated.definition() == before.definition():
        return before, None
    uow.schedule.save(updated, actor.user_id)
    operation = change_log.record(
        uow,
        actor,
        "schedule.update",
        f"Pago programado «{updated.name}» cambiado",
        [
            Change(
                Entity.SCHEDULE,
                str(schedule_id),
                "definition",
                before.definition(),
                updated.definition(),
            )
        ],
        now,
    )
    uow.commit()
    return updated, operation.id if operation else None


def delete_payment(uow: UnitOfWork, actor: Actor, schedule_id: UUID, now: datetime) -> UUID | None:
    payment = _own(uow, actor, schedule_id)
    uow.schedule.delete(actor.household_id, schedule_id)
    operation = change_log.record(
        uow,
        actor,
        "schedule.delete",
        f"Pago programado «{payment.name}» borrado",
        [Change(Entity.SCHEDULE, str(schedule_id), "definition", payment.definition(), None)],
        now,
    )
    uow.commit()
    return operation.id if operation else None


def list_schedule(
    uow: UnitOfWork, actor: Actor, today: date, days: int = DEFAULT_HORIZON_DAYS
) -> list[PaymentView]:
    """Los pagos visibles con sus ocurrencias recientes y de los próximos ``days`` días."""
    if not 1 <= days <= MAX_HORIZON_DAYS:
        raise InvalidRequestError(f"El horizonte va de 1 a {MAX_HORIZON_DAYS} días")
    until = today + timedelta(days=days)
    oldest = today - timedelta(days=LATE_WINDOW_DAYS + MATCH_DAYS)
    newest = until + timedelta(days=MATCH_DAYS)
    cache: dict[AccountId, list[Transaction]] = {}
    views: list[PaymentView] = []
    for payment in visible_payments(uow, actor):
        if payment.account_id not in cache:
            cache[payment.account_id] = [
                t
                for t in uow.transactions.for_account(actor.household_id, payment.account_id)
                if oldest <= t.booked_at.date() <= newest
            ]
        views.append(
            PaymentView(payment, upcoming(payment, cache[payment.account_id], today, until))
        )
    return views
