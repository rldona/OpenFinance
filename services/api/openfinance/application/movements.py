"""Clasificar varios a la vez, y altas y bajas de movimientos manuales (OF-705, ADR-0017)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from openfinance.application.changes import record, transaction_state
from openfinance.application.errors import InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import CategoryId
from openfinance.domain.changes import Change, Entity, diff
from openfinance.domain.ledger import LedgerError, Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.domain.workspaces import Actor

MAX_BULK = 500
MANUAL_SOURCE = "manual"
MANUAL_KINDS = (TransactionKind.EXPENSE, TransactionKind.INCOME)


@dataclass(frozen=True, slots=True)
class BulkResult:
    updated: int
    operation_id: UUID | None


def categorize_many(
    uow: UnitOfWork,
    actor: Actor,
    ids: list[TransactionId],
    category_id: CategoryId | None,
    now: datetime,
) -> BulkResult:
    """Pone (o quita) la misma categoría a varios gastos, sin aprender reglas.

    Es una sola operación: «Deshacer» los devuelve a todos como estaban. Si alguno no existe
    o no se puede ver, no se toca ninguno (404).
    """
    unique = list(dict.fromkeys(ids))
    if not unique or len(unique) > MAX_BULK:
        raise InvalidRequestError(f"Elige entre 1 y {MAX_BULK} movimientos")
    name = "Sin categoría"
    if category_id is not None:
        category = uow.categories.get(actor.household_id, category_id)
        if category is None:
            raise NotFoundError("Categoría no encontrada")
        if category.hidden:
            raise InvalidRequestError(f"La categoría «{category.name}» está oculta")
        name = category.name
    visible = {a.id for a in visible_accounts(uow, actor)}
    targets: list[Transaction] = []
    for transaction_id in unique:
        t = uow.transactions.get(actor.household_id, transaction_id)
        if t is None or t.account_id not in visible:
            raise NotFoundError("Movimiento no encontrado")
        if t.kind is not TransactionKind.EXPENSE:
            raise InvalidRequestError("Solo los gastos tienen categoría")
        targets.append(t)
    changes: list[Change] = []
    for t in targets:
        updated = replace(t, category_id=category_id)
        changes += diff(
            Entity.TRANSACTION, str(t.id), transaction_state(t), transaction_state(updated)
        )
        uow.transactions.save(updated)
    count = len(changes)
    summary = f"→ {name}"  # el número de gastos lo pone display_summary
    operation = record(uow, actor, "transactions.categorize", summary, changes, now)
    uow.commit()
    return BulkResult(count, operation.id if operation else None)


@dataclass(frozen=True, slots=True)
class NewManual:
    account_id: AccountId
    booked_on: date
    description: str
    amount: str
    """Siempre positivo: el signo lo da el tipo (un gasto resta)."""
    kind: TransactionKind = TransactionKind.EXPENSE
    category_id: CategoryId | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class ManualResult:
    transaction: Transaction
    operation_id: UUID | None


def add_manual(uow: UnitOfWork, actor: Actor, spec: NewManual, now: datetime) -> ManualResult:
    """Alta de un movimiento que no viene de ningún extracto, p. ej. un pago en efectivo."""
    account = next((a for a in visible_accounts(uow, actor) if a.id == spec.account_id), None)
    if account is None:
        raise NotFoundError("Cuenta no encontrada")
    if spec.kind not in MANUAL_KINDS:
        raise InvalidRequestError("A mano solo se añaden gastos o ingresos")
    if spec.category_id is not None:
        category = uow.categories.get(actor.household_id, spec.category_id)
        if category is None:
            raise NotFoundError("Categoría no encontrada")
        if category.hidden:
            raise InvalidRequestError(f"La categoría «{category.name}» está oculta")
    try:
        value = Decimal(spec.amount.replace(",", "."))
    except InvalidOperation as exc:
        raise InvalidRequestError("Importe no válido") from exc
    if value <= 0:
        raise InvalidRequestError("El importe tiene que ser mayor que cero")
    signed = -value if spec.kind is TransactionKind.EXPENSE else value
    description = " ".join(spec.description.split())
    if not description:
        raise InvalidRequestError("Escribe un concepto")
    try:
        transaction = Transaction(
            id=TransactionId(uuid4()),
            household_id=actor.household_id,
            account_id=account.id,
            booked_at=datetime.combine(spec.booked_on, time(12)),
            value_date=spec.booked_on,
            description=description,
            amount=Money.of(signed, account.currency),
            kind=spec.kind,
            category_id=spec.category_id,
            source=MANUAL_SOURCE,
            note=" ".join(spec.note.split()),
        )
    except (LedgerError, ValueError) as exc:
        raise InvalidRequestError(str(exc)) from exc
    uow.transactions.add(transaction)
    # El alta se registra como «anulado → activo»: deshacerla es anularlo.
    change = Change(Entity.TRANSACTION, str(transaction.id), "voided", True, False)
    summary = f"Añadido a mano: {description}"
    operation = record(uow, actor, "transaction.create", summary, [change], now)
    uow.commit()
    return ManualResult(transaction, operation.id if operation else None)


def delete_manual(
    uow: UnitOfWork, actor: Actor, transaction_id: TransactionId, now: datetime
) -> UUID | None:
    """Anula un movimiento manual. Queda en el registro y se puede deshacer.

    Los importados no se borran: se deshace su importación entera (OF-703).
    """
    t = uow.transactions.get(actor.household_id, transaction_id)
    if t is None or t.account_id not in {a.id for a in visible_accounts(uow, actor)}:
        raise NotFoundError("Movimiento no encontrado")
    if t.import_id is not None or t.source != MANUAL_SOURCE:
        raise InvalidRequestError(
            "Los movimientos importados no se borran; puedes deshacer su importación"
        )
    uow.transactions.save(replace(t, voided=True))
    change = Change(Entity.TRANSACTION, str(t.id), "voided", False, True)
    operation = record(uow, actor, "transaction.delete", f"Borrado: {t.description}", [change], now)
    uow.commit()
    return operation.id if operation else None
