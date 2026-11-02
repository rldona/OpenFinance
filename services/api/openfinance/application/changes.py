"""Registro de cambios: registrar, consultar, deshacer y rehacer (ADR-0017).

Deshacer pone el valor anterior solo donde el valor actual sigue siendo el que dejó la
operación. Si alguien lo cambió después, ese cambio se respeta y se informa de quién fue.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from openfinance.application.errors import ConflictError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.automation import from_definition
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
from openfinance.domain.merchants import Merchant, MerchantId, join_keys, split_keys
from openfinance.domain.rates import ExchangeRate
from openfinance.domain.shared import Currency
from openfinance.domain.shared.ids import AccountId, TransactionId, UserId
from openfinance.domain.splits import decode_parts, encode_parts
from openfinance.domain.tags import join_tags, split_tags
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
        "reviewed": t.reviewed,
        "merchant": t.merchant,
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
        reviewed=bool(state["reviewed"]),
        merchant=str(state["merchant"] or ""),
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


def display_summary(operation: Operation, visible: set[str] | None = None) -> str:
    """El resumen con el número de movimientos que puede ver quien lo lee.

    ``visible`` son los movimientos que ve (``None`` = todos, para su autor). Una regla del
    hogar aprendida por la pareja también clasifica sus cuentas personales: contarlos aquí
    revelaría cuántos movimientos tiene allí (ADR-0013).
    """
    ids = list(
        dict.fromkeys(c.entity_id for c in operation.changes if c.entity is Entity.TRANSACTION)
    )
    n = len(ids) if visible is None else sum(1 for i in ids if i in visible)
    base = operation.summary
    if operation.action == "transaction.edit" and n > 1:
        return f"{base} y {n - 1} más"
    if operation.action == "transactions.categorize":
        return f"{n} {'gasto' if n == 1 else 'gastos'} {base}"
    if operation.action == "transactions.review":
        return f"{n} {'movimiento' if n == 1 else 'movimientos'} {base}"
    if operation.action == "import.undo":
        return f"{base} ({n} movimientos)"
    return base


@dataclass(frozen=True, slots=True)
class HistoryItem:
    operation: Operation
    summary: str
    """Contado solo sobre lo que ve quien pregunta."""
    changes: list[Change]
    """Solo los cambios de ese movimiento."""


def transaction_history(
    uow: UnitOfWork, actor: Actor, transaction_id: TransactionId
) -> list[HistoryItem]:
    """Correcciones de un movimiento, de cualquier persona, si quien pregunta lo puede ver."""
    _visible_transaction(uow, actor, transaction_id)
    key = str(transaction_id)
    operations = uow.changes.touching(actor.household_id, Entity.TRANSACTION, [key])
    ids = {
        TransactionId(UUID(c.entity_id))
        for o in operations
        for c in o.changes
        if c.entity is Entity.TRANSACTION
    }
    accounts = {a.id for a in visible_accounts(uow, actor)}
    visible = {
        str(t)
        for t, account in uow.transactions.accounts_of(actor.household_id, list(ids)).items()
        if account in accounts
    }
    return [
        HistoryItem(
            o,
            display_summary(o, None if o.actor_id == actor.user_id else visible),
            [c for c in o.changes if c.entity is Entity.TRANSACTION and c.entity_id == key],
        )
        for o in operations
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
        elif entity is Entity.AUTOMATION:
            done, rest = _apply_automation(uow, actor, entity_id, changes)
        elif entity is Entity.RATE:
            done, rest = _apply_rate(uow, actor, entity_id, changes)
        elif entity is Entity.ATTACHMENT:
            done, rest = _apply_attachment(uow, actor, visible, entity_id, changes, now)
        elif entity is Entity.LINK:
            done, rest = _apply_link(uow, actor, visible, entity_id, changes)
        elif entity is Entity.SPLIT:
            done, rest = _apply_split(uow, actor, visible, entity_id, changes)
        elif entity is Entity.MERCHANT:
            done, rest = _apply_merchant(uow, actor, entity_id, changes)
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
    tag_changes = [c for c in changes if c.field == "tags"]
    changes = [c for c in changes if c.field != "tags"]
    for c in changes:
        if current.get(c.field) == c.before and c.field not in values:
            values[c.field] = c.after
        else:
            kept.append(c)
    applied_tags = _apply_tags(uow, actor, t, tag_changes, kept)
    if not values:
        return applied_tags, kept
    try:
        updated = with_state(t, values)
    except LedgerError:
        # Lo que queda no formaría un movimiento válido (p. ej. persona sin aportación).
        return 0, changes
    uow.transactions.save(updated)
    return len(values) + applied_tags, kept


def _apply_tags(
    uow: UnitOfWork, actor: Actor, t: Transaction, changes: list[Change], kept: list[Change]
) -> int:
    """Etiquetas de un movimiento (OF-1002): «a|b|c», o ``None`` si no tiene ninguna."""
    if not changes:
        return 0
    start = uow.tags.for_transactions(actor.household_id, [t.id]).get(t.id, ())
    state, applied = join_tags(start) or None, 0
    for c in changes:
        if state == c.before:
            state = None if c.after is None else str(c.after)
            applied += 1
        else:
            kept.append(c)
    if applied:
        uow.tags.set(actor.household_id, t.id, split_tags(state or ""))
    return applied


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


def _apply_automation(
    uow: UnitOfWork, actor: Actor, entity_id: str, changes: list[Change]
) -> tuple[int, list[Change]]:
    """Una regla con condiciones (OF-1101): ``definition`` es su texto canónico o ``None``."""
    rule_id = UUID(entity_id)
    current = uow.automation.get(actor.household_id, rule_id)
    applied, kept = 0, []
    for c in changes:
        state = current.definition() if current else None
        # La regla personal de otra persona no se toca (ni existe para quien deshace).
        foreign = current is not None and current.scope not in ("", str(actor.user_id))
        if c.field != "definition" or state != c.before or foreign:
            kept.append(c)
            continue
        if c.after is None:
            uow.automation.delete(actor.household_id, rule_id)
            current = None
        else:
            current = from_definition(rule_id, actor.household_id, str(c.after))
            if current.scope not in ("", str(actor.user_id)):
                kept.append(c)
                continue
            uow.automation.save(current, actor.user_id)
        applied += 1
    return applied, kept


def _apply_rate(
    uow: UnitOfWork, actor: Actor, entity_id: str, changes: list[Change]
) -> tuple[int, list[Change]]:
    """Un tipo de cambio (OF-1008): ``rate`` = valor como texto, o ``None`` si no existe."""
    code, _, day = entity_id.partition("|")
    currency, on = Currency(code), date.fromisoformat(day)
    current = uow.rates.get(actor.household_id, currency, on)
    state = f"{current.rate:f}" if current else None
    applied, kept = 0, []
    for c in changes:
        if c.field != "rate" or state != c.before:
            kept.append(c)
            continue
        if c.after is None:
            uow.rates.delete(actor.household_id, currency, on)
        else:
            uow.rates.upsert(
                ExchangeRate(actor.household_id, currency, on, Decimal(str(c.after))),
                actor.user_id,
            )
        state = None if c.after is None else str(c.after)
        applied += 1
    return applied, kept


def _apply_attachment(
    uow: UnitOfWork,
    actor: Actor,
    visible: set[AccountId],
    entity_id: str,
    changes: list[Change],
    now: datetime,
) -> tuple[int, list[Change]]:
    """Un adjunto está o no está (OF-1007). Borrar conserva el archivo, así que se recupera."""
    attachment = uow.attachments.get(actor.household_id, UUID(entity_id))
    if attachment is None:
        return 0, changes
    t = uow.transactions.get(actor.household_id, attachment.transaction_id, include_voided=True)
    if t is None or t.account_id not in visible:
        return 0, changes
    present = not attachment.is_deleted
    applied, kept = 0, []
    for c in changes:
        if c.field != "present" or present != c.before:
            kept.append(c)
            continue
        uow.attachments.set_deleted(actor.household_id, attachment.id, None if c.after else now)
        present = bool(c.after)
        applied += 1
    return applied, kept


def _apply_link(
    uow: UnitOfWork,
    actor: Actor,
    visible: set[AccountId],
    entity_id: str,
    changes: list[Change],
) -> tuple[int, list[Change]]:
    """Enlace de un traspaso (OF-1004): ``peer`` es el otro lado o ``None``."""
    first = TransactionId(UUID(entity_id))
    state = uow.links.peers(actor.household_id, [first]).get(first)
    current = str(state) if state else None
    applied, kept = 0, []
    for c in changes:
        if c.field != "peer" or current != c.before:
            kept.append(c)
            continue
        other = TransactionId(UUID(str(c.after if c.after is not None else c.before)))
        accounts = uow.transactions.accounts_of(actor.household_id, [first, other])
        if not {accounts.get(first), accounts.get(other)} <= visible:
            kept.append(c)  # quien no ve alguno de los dos lados no lo toca
            continue
        if c.after is None:
            uow.links.unlink(actor.household_id, first)
        else:
            uow.links.link(actor.household_id, first, other)
        current = None if c.after is None else str(c.after)
        applied += 1
    return applied, kept


def _apply_split(
    uow: UnitOfWork,
    actor: Actor,
    visible: set[AccountId],
    entity_id: str,
    changes: list[Change],
) -> tuple[int, list[Change]]:
    """Partes de un movimiento dividido (OF-1003)."""
    tid = TransactionId(UUID(entity_id))
    t = uow.transactions.get(actor.household_id, tid, include_voided=True)
    if t is None or t.account_id not in visible:
        return 0, changes
    state = encode_parts(uow.splits.for_transactions(actor.household_id, [tid]).get(tid, []))
    applied, kept = 0, []
    for c in changes:
        if c.field == "parts" and state == c.before:
            state = None if c.after is None else str(c.after)
            applied += 1
        else:
            kept.append(c)
    if applied:
        uow.splits.set(actor.household_id, tid, decode_parts(state, t.amount.currency.code))
    return applied, kept


def _apply_merchant(
    uow: UnitOfWork, actor: Actor, entity_id: str, changes: list[Change]
) -> tuple[int, list[Change]]:
    """Nombre y variantes de un comercio (OF-1001). ``name`` = ``None`` es «no existe».

    Los cambios se recorren en orden sobre un estado en memoria y el resultado se escribe una
    sola vez: así da igual en qué orden lleguen el nombre y las variantes de un mismo comercio.
    """
    merchant_id = MerchantId(UUID(entity_id))
    merchant = uow.merchants.get(actor.household_id, merchant_id)
    start_name = merchant.name if merchant else None
    start_keys = join_keys(merchant.keys) if merchant else None
    name, keys = start_name, start_keys
    applied, kept = 0, []
    for c in changes:
        if c.field == "name" and name == c.before:
            name = None if c.after is None else str(c.after)
            applied += 1
        elif c.field == "keys" and keys == c.before:
            keys = None if c.after is None else str(c.after)
            applied += 1
        else:
            kept.append(c)
    if name is None:
        if merchant is not None:
            uow.merchants.delete(actor.household_id, merchant_id)
        return applied, kept
    if merchant is None:
        uow.merchants.add(Merchant(merchant_id, actor.household_id, name, ()))
    elif name != start_name:
        uow.merchants.set_name(actor.household_id, merchant_id, name)
    if keys is not None and keys != start_keys:
        uow.merchants.set_keys(actor.household_id, merchant_id, split_keys(keys))
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
