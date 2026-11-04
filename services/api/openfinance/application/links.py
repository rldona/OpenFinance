"""Traspasos enlazados entre cuentas propias (OF-1004).

Solo se enlazan movimientos de cuentas que ve quien enlaza. Quien no ve el otro lado no sabe
que existe: ni en el movimiento ni en el listado (ADR-0013).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from openfinance.application import changes as change_log
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.changes import Change, Entity
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.links import (
    LINKABLE_TO_TRANSFER,
    WINDOW_DAYS,
    LinkError,
    pair,
    validate_link,
)
from openfinance.domain.shared.ids import TransactionId
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class LinkResult:
    transaction: Transaction
    peer: Transaction
    operation_id: UUID | None


def _visible(uow: UnitOfWork, actor: Actor, transaction_id: TransactionId) -> Transaction:
    t = uow.transactions.get(actor.household_id, transaction_id)
    visible = {a.id for a in visible_accounts(uow, actor)}
    if t is None or t.account_id not in visible:
        raise NotFoundError("Movimiento no encontrado")
    return t


def candidates(uow: UnitOfWork, actor: Actor, transaction_id: TransactionId) -> list[Transaction]:
    """Posibles otros lados de un traspaso, solo entre las cuentas que ve quien pregunta."""
    t = _visible(uow, actor, transaction_id)
    accounts = [a.id for a in visible_accounts(uow, actor)]
    return uow.transactions.transfer_candidates(actor.household_id, accounts, t, WINDOW_DAYS)


def link_transfer(
    uow: UnitOfWork,
    actor: Actor,
    transaction_id: TransactionId,
    peer_id: TransactionId,
    now: datetime,
) -> LinkResult:
    a = _visible(uow, actor, transaction_id)
    b = _visible(uow, actor, peer_id)
    try:
        validate_link(a, b)
    except LinkError as exc:
        raise InvalidRequestError(str(exc)) from exc
    if uow.links.peers(actor.household_id, [a.id, b.id]):
        raise ConflictError("Alguno de los dos movimientos ya está enlazado a otro traspaso")
    first, second = pair(a, b)
    changes = [Change(Entity.LINK, str(first.id), "peer", None, str(second.id))]
    sides: dict[TransactionId, Transaction] = {a.id: a, b.id: b}
    for side in (a, b):
        if side.kind not in LINKABLE_TO_TRANSFER:
            continue
        moved = replace(side, kind=TransactionKind.INTERNAL_TRANSFER, category_id=None)
        changes.append(
            Change(Entity.TRANSACTION, str(side.id), "kind", side.kind.value, moved.kind.value)
        )
        if side.category_id is not None:
            changes.append(
                Change(Entity.TRANSACTION, str(side.id), "category_id", str(side.category_id), None)
            )
        uow.transactions.save(moved)
        sides[side.id] = moved
    uow.links.link(actor.household_id, a.id, b.id)
    operation = change_log.record(
        uow,
        actor,
        "transfer.link",
        f"Traspaso enlazado: «{a.description}» y «{b.description}»",
        changes,
        now,
    )
    uow.commit()
    return LinkResult(sides[a.id], sides[b.id], operation.id if operation else None)


def unlink_transfer(
    uow: UnitOfWork, actor: Actor, transaction_id: TransactionId, now: datetime
) -> LinkResult:
    a = _visible(uow, actor, transaction_id)
    peer_id = uow.links.peers(actor.household_id, [a.id]).get(a.id)
    visible = {x.id for x in visible_accounts(uow, actor)}
    b = uow.transactions.get(actor.household_id, peer_id) if peer_id else None
    # Quien no ve el otro lado no sabe que el enlace existe: para él no está enlazado.
    if b is None or b.account_id not in visible:
        raise InvalidRequestError("Este movimiento no está enlazado")
    first, second = pair(a, b)
    uow.links.unlink(actor.household_id, a.id)
    operation = change_log.record(
        uow,
        actor,
        "transfer.unlink",
        f"Traspaso desenlazado: «{a.description}» y «{b.description}»",
        [Change(Entity.LINK, str(first.id), "peer", str(second.id), None)],
        now,
    )
    uow.commit()
    return LinkResult(a, b, operation.id if operation else None)
