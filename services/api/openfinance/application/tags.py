"""Etiquetas de movimientos (OF-1002).

Una etiqueta es una palabra libre del hogar. Se ve y se cambia lo mismo que el movimiento:
las de un movimiento de una cuenta personal ajena no se ven ni en el listado de etiquetas ni
en los filtros (ADR-0013).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from openfinance.application import changes as change_log
from openfinance.application.errors import InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.changes import Change, Entity
from openfinance.domain.ledger import Transaction
from openfinance.domain.shared.ids import TransactionId, WorkspaceId
from openfinance.domain.tags import TagError, clean_tags, join_tags
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class TagsResult:
    transaction: Transaction
    tags: tuple[str, ...]
    operation_id: UUID | None


def list_tags(uow: UnitOfWork, actor: Actor) -> list[tuple[str, int]]:
    """(etiqueta, movimientos) solo de lo que ve quien pregunta."""
    accounts = [a.id for a in visible_accounts(uow, actor)]
    return uow.tags.counts(actor.household_id, accounts)


def tags_for(
    uow: UnitOfWork, household_id: WorkspaceId, transactions: Iterable[Transaction]
) -> dict[TransactionId, tuple[str, ...]]:
    return uow.tags.for_transactions(household_id, [t.id for t in transactions])


def set_transaction_tags(
    uow: UnitOfWork,
    actor: Actor,
    transaction_id: TransactionId,
    raw_tags: list[str],
    now: datetime,
) -> TagsResult:
    """Sustituye las etiquetas de un movimiento y lo anota para poder deshacerlo."""
    t = uow.transactions.get(actor.household_id, transaction_id)
    visible = {a.id for a in visible_accounts(uow, actor)}
    if t is None or t.account_id not in visible:
        raise NotFoundError("Movimiento no encontrado")
    try:
        tags = clean_tags(raw_tags)
    except TagError as exc:
        raise InvalidRequestError(str(exc)) from exc
    current = uow.tags.for_transactions(actor.household_id, [t.id]).get(t.id, ())
    before, after = join_tags(current) or None, join_tags(tags) or None
    if before == after:
        return TagsResult(t, current, None)
    uow.tags.set(actor.household_id, t.id, tags)
    operation = change_log.record(
        uow,
        actor,
        "transaction.tags",
        f"Etiquetas de {t.description}",
        [Change(Entity.TRANSACTION, str(t.id), "tags", before, after)],
        now,
    )
    uow.commit()
    return TagsResult(t, tags, operation.id if operation else None)
