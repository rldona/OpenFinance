"""Dividir un movimiento en partes con categoría y deshacer la división (OF-1003).

Solo se dividen gastos (o devoluciones) de cuentas que ve quien divide. Dividir deja el
movimiento sin categoría propia: la tienen sus partes. Los informes cuentan las partes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from openfinance.application import changes as change_log
from openfinance.application.errors import InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import CategoryId
from openfinance.domain.changes import Change, Entity
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId
from openfinance.domain.splits import SplitError, SplitPart, encode_parts, validate_split
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class SplitResult:
    transaction: Transaction
    parts: list[SplitPart]
    operation_id: UUID | None


def _visible_expense(uow: UnitOfWork, actor: Actor, transaction_id: TransactionId) -> Transaction:
    t = uow.transactions.get(actor.household_id, transaction_id)
    visible = {a.id for a in visible_accounts(uow, actor)}
    if t is None or t.account_id not in visible:
        raise NotFoundError("Movimiento no encontrado")
    if t.kind is not TransactionKind.EXPENSE:
        raise InvalidRequestError("Solo se pueden dividir los gastos")
    return t


def split_transaction(
    uow: UnitOfWork,
    actor: Actor,
    transaction_id: TransactionId,
    raw_parts: list[tuple[str, CategoryId]],
    now: datetime,
) -> SplitResult:
    """Divide (o vuelve a dividir) un gasto. ``raw_parts``: (importe en texto, categoría)."""
    t = _visible_expense(uow, actor, transaction_id)
    parts: list[SplitPart] = []
    for amount, category_id in raw_parts:
        category = uow.categories.get(actor.household_id, category_id)
        if category is None:
            raise NotFoundError("Categoría no encontrada")
        if category.hidden:
            raise InvalidRequestError(f"La categoría «{category.name}» está oculta")
        try:
            parts.append(SplitPart(Money.of(amount, t.amount.currency), category_id))
        except ValueError as exc:
            raise InvalidRequestError(f"Importe no válido: {amount}") from exc
    try:
        validate_split(t.amount, parts)
    except SplitError as exc:
        raise InvalidRequestError(str(exc)) from exc
    return _store(uow, actor, t, parts, now, f"Dividido «{t.description}» en {len(parts)} partes")


def unsplit_transaction(
    uow: UnitOfWork, actor: Actor, transaction_id: TransactionId, now: datetime
) -> SplitResult:
    t = _visible_expense(uow, actor, transaction_id)
    if t.id not in uow.splits.for_transactions(actor.household_id, [t.id]):
        raise InvalidRequestError("Este movimiento no está dividido")
    return _store(uow, actor, t, [], now, f"Deshecha la división de «{t.description}»")


def _store(
    uow: UnitOfWork,
    actor: Actor,
    t: Transaction,
    parts: list[SplitPart],
    now: datetime,
    summary: str,
) -> SplitResult:
    before_parts = uow.splits.for_transactions(actor.household_id, [t.id]).get(t.id, [])
    changes: list[Change] = []
    entity_id = str(t.id)
    changes.append(
        Change(Entity.SPLIT, entity_id, "parts", encode_parts(before_parts), encode_parts(parts))
    )
    updated = t
    if parts and t.category_id is not None:
        # Con partes, la categoría está en ellas y el movimiento se queda sin la suya.
        updated = replace(t, category_id=None)
        changes.append(
            Change(Entity.TRANSACTION, entity_id, "category_id", str(t.category_id), None)
        )
        uow.transactions.save(updated)
    uow.splits.set(actor.household_id, t.id, parts)
    operation = change_log.record(
        uow, actor, "transaction.split" if parts else "transaction.unsplit", summary, changes, now
    )
    uow.commit()
    return SplitResult(updated, parts, operation.id if operation else None)
