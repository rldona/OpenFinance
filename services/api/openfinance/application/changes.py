"""Registro de cambios: registrar, consultar, deshacer y rehacer (ADR-0017).

Deshacer pone el valor anterior solo donde el valor actual sigue siendo el que dejó la
operación. Si alguien lo cambió después, ese cambio se respeta y se informa de quién fue.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from openfinance.application.errors import ConflictError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import HOUSEHOLD_SCOPE, CategoryId, CategoryRule
from openfinance.domain.changes import (
    Change,
    Entity,
    Operation,
    Value,
    split_rule_entity_id,
)
from openfinance.domain.imports.batch import ImportStatus
from openfinance.domain.ledger import LedgerError, Transaction, TransactionKind
from openfinance.domain.shared.ids import AccountId, TransactionId, UserId
from openfinance.domain.workspaces import Actor

MAX_SUMMARY = 200
RECENT_OPERATIONS = 50


def transaction_state(t: Transaction) -> dict[str, Value]:
    """Los campos corregibles de un movimiento, tal como se guardan en el registro."""
    return {
        "kind": t.kind.value,
        "member_id": str(t.member_id) if t.member_id else None,
        "category_id": str(t.category_id) if t.category_id else None,
        "note": t.note,
        "voided": t.voided,
    }


def with_state(t: Transaction, values: Mapping[str, Value]) -> Transaction:
    """El movimiento con esos campos. Lanza ``LedgerError`` si el resultado no es válido."""
    state = {**transaction_state(t), **values}
    member, category = state["member_id"], state["category_id"]
    return replace(
        t,
        kind=TransactionKind(str(state["kind"])),
        member_id=UserId(UUID(str(member))) if member else None,
        category_id=CategoryId(UUID(str(category))) if category else None,
        note=str(state["note"] or ""),
        voided=bool(state["voided"]),
    )


def record(
    uow: UnitOfWork,
    actor: Actor,
    action: str,
    summary: str,
    changes: Sequence[Change],
    now: datetime,
) -> Operation | None:
    """Guarda la operación si cambia algo. Quien llama hace ``commit``."""
    if not changes:
        return None
    operation = Operation(
        id=uuid4(),
        household_id=actor.household_id,
        actor_id=actor.user_id,
        created_at=now,
        action=action,
        summary=summary[:MAX_SUMMARY],
        changes=tuple(changes),
    )
    uow.changes.add(operation)
    return operation


@dataclass(frozen=True, slots=True)
class RevertResult:
    operation: Operation
    applied: int
    kept: int
    """Cambios que no se han tocado porque alguien los cambió después."""
    kept_by: list[UserId]
    """Quién hizo esos cambios posteriores."""


def undo(uow: UnitOfWork, actor: Actor, operation_id: UUID, now: datetime) -> RevertResult:
    """Deshace una operación propia."""
    operation = _own(uow, actor, operation_id)
    if operation.is_undone:
        raise ConflictError("Esta operación ya está deshecha")
    plan = [c.inverse() for c in reversed(operation.changes)]
    applied, kept = _apply(uow, actor, plan, now)
    uow.changes.mark_undone(operation.id, now, actor.user_id)
    result = RevertResult(
        replace(operation, undone_at=now, undone_by=actor.user_id),
        applied,
        len(kept),
        _later_authors(uow, operation, kept),
    )
    uow.commit()
    return result


def redo(uow: UnitOfWork, actor: Actor, operation_id: UUID, now: datetime) -> RevertResult:
    """Vuelve a aplicar una operación propia que se había deshecho."""
    operation = _own(uow, actor, operation_id)
    if not operation.is_undone:
        raise ConflictError("Esta operación no está deshecha")
    applied, kept = _apply(uow, actor, list(operation.changes), now)
    uow.changes.mark_undone(operation.id, None, None)
    result = RevertResult(
        replace(operation, undone_at=None, undone_by=None),
        applied,
        len(kept),
        _later_authors(uow, operation, kept),
    )
    uow.commit()
    return result


def recent_operations(uow: UnitOfWork, actor: Actor) -> list[Operation]:
    """Las últimas operaciones de quien pregunta. Nunca las de otra persona."""
    return uow.changes.for_actor(actor.household_id, actor.user_id, RECENT_OPERATIONS)


@dataclass(frozen=True, slots=True)
class HistoryItem:
    operation: Operation
    changes: list[Change]
    """Solo los cambios de ese movimiento."""


def transaction_history(
    uow: UnitOfWork, actor: Actor, transaction_id: TransactionId
) -> list[HistoryItem]:
    """Correcciones de un movimiento, de cualquier persona, si quien pregunta lo puede ver."""
    _visible_transaction(uow, actor, transaction_id)
    key = str(transaction_id)
    return [
        HistoryItem(
            o, [c for c in o.changes if c.entity is Entity.TRANSACTION and c.entity_id == key]
        )
        for o in uow.changes.touching(actor.household_id, Entity.TRANSACTION, [key])
    ]


def _own(uow: UnitOfWork, actor: Actor, operation_id: UUID) -> Operation:
    operation = uow.changes.get(actor.household_id, operation_id)
    # Una operación de la pareja no se puede deshacer, y ni siquiera se confirma que existe.
    if operation is None or operation.actor_id != actor.user_id:
        raise NotFoundError("Operación no encontrada")
    return operation


def _visible_transaction(
    uow: UnitOfWork, actor: Actor, transaction_id: TransactionId
) -> Transaction:
    t = uow.transactions.get(actor.household_id, transaction_id, include_voided=True)
    visible = {a.id for a in visible_accounts(uow, actor)}
    if t is None or t.account_id not in visible:
        raise NotFoundError("Movimiento no encontrado")
    return t


def _apply(
    uow: UnitOfWork, actor: Actor, plan: Sequence[Change], now: datetime
) -> tuple[int, list[Change]]:
    """Aplica los cambios cuyo valor actual es su «antes». Devuelve (aplicados, respetados)."""
    applied = 0
    kept: list[Change] = []
    groups: dict[tuple[Entity, str], list[Change]] = {}
    for c in plan:
        groups.setdefault((c.entity, c.entity_id), []).append(c)
    visible = {a.id for a in visible_accounts(uow, actor)}
    for (entity, entity_id), changes in groups.items():
        if entity is Entity.TRANSACTION:
            done, rest = _apply_transaction(uow, actor, visible, entity_id, changes)
        elif entity is Entity.RULE:
            done, rest = _apply_rule(uow, actor, entity_id, changes, now)
        else:
            done, rest = _apply_import(uow, actor, entity_id, changes)
        applied += done
        kept += rest
    return applied, kept


def _apply_transaction(
    uow: UnitOfWork,
    actor: Actor,
    visible: set[AccountId],
    entity_id: str,
    changes: list[Change],
) -> tuple[int, list[Change]]:
    t = uow.transactions.get(
        actor.household_id, TransactionId(UUID(entity_id)), include_voided=True
    )
    if t is None or t.account_id not in visible:
        return 0, changes
    current = transaction_state(t)
    values: dict[str, Value] = {}
    kept: list[Change] = []
    for c in changes:
        if current.get(c.field) == c.before and c.field not in values:
            values[c.field] = c.after
        else:
            kept.append(c)
    if not values:
        return 0, kept
    try:
        updated = with_state(t, values)
    except LedgerError:
        # Lo que queda no formaría un movimiento válido (p. ej. persona sin aportación).
        return 0, changes
    uow.transactions.save(updated)
    return len(values), kept


def _apply_rule(
    uow: UnitOfWork, actor: Actor, entity_id: str, changes: list[Change], now: datetime
) -> tuple[int, list[Change]]:
    scope, merchant = split_rule_entity_id(entity_id)
    if scope not in (HOUSEHOLD_SCOPE, str(actor.user_id)):
        return 0, changes  # una regla personal solo la toca su titular
    applied, kept = 0, []
    for c in changes:
        rule = uow.rules.get(actor.household_id, scope, merchant)
        current = str(rule.category_id) if rule else None
        if c.field != "category_id" or current != c.before:
            kept.append(c)
            continue
        if c.after is None:
            uow.rules.delete(actor.household_id, scope, merchant)
        else:
            uow.rules.upsert(
                CategoryRule(actor.household_id, merchant, CategoryId(UUID(str(c.after))), scope),
                now,
            )
        applied += 1
    return applied, kept


def _apply_import(
    uow: UnitOfWork, actor: Actor, entity_id: str, changes: list[Change]
) -> tuple[int, list[Change]]:
    batch = uow.imports.get(actor.household_id, UUID(entity_id))
    applied, kept = 0, []
    for c in changes:
        current = batch.status.value if batch else None
        if batch is None or c.field != "status" or current != c.before:
            kept.append(c)
            continue
        uow.imports.set_status(batch.id, ImportStatus(str(c.after)))
        batch = replace(batch, status=ImportStatus(str(c.after)))
        applied += 1
    return applied, kept


def _later_authors(uow: UnitOfWork, operation: Operation, kept: Sequence[Change]) -> list[UserId]:
    """Quién cambió después lo que no se ha podido deshacer."""
    keys = {c.key for c in kept}
    if not keys:
        return []
    authors: list[UserId] = []
    by_entity: dict[Entity, list[str]] = {}
    for entity, entity_id, _ in keys:
        by_entity.setdefault(entity, []).append(entity_id)
    for entity, ids in by_entity.items():
        for o in uow.changes.touching(operation.household_id, entity, ids):
            if o.id == operation.id or o.created_at < operation.created_at:
                continue
            if any(c.key in keys for c in o.changes) and o.actor_id not in authors:
                authors.append(o.actor_id)
    return authors
