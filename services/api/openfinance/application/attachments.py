"""Adjuntos de movimientos: tickets y facturas (OF-1007).

Un adjunto se ve y se cambia lo mismo que su movimiento (ADR-0013): quien no ve el movimiento
no sabe que tiene adjuntos. Borrar no destruye: el archivo se conserva 30 días para poder
deshacer, y después se purga.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from openfinance.application import changes as change_log
from openfinance.application.errors import InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import AttachmentStore, UnitOfWork
from openfinance.domain.attachments import (
    MAX_PER_TRANSACTION,
    Attachment,
    AttachmentError,
    clean_filename,
    validate,
)
from openfinance.domain.changes import Change, Entity
from openfinance.domain.ledger import Transaction
from openfinance.domain.shared.ids import TransactionId
from openfinance.domain.workspaces import Actor

KEEP_DELETED = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class AttachmentResult:
    attachment: Attachment
    operation_id: UUID | None


def _visible_transaction(
    uow: UnitOfWork, actor: Actor, transaction_id: TransactionId
) -> Transaction:
    t = uow.transactions.get(actor.household_id, transaction_id)
    visible = {a.id for a in visible_accounts(uow, actor)}
    if t is None or t.account_id not in visible:
        raise NotFoundError("Movimiento no encontrado")
    return t


def list_attachments(
    uow: UnitOfWork, actor: Actor, transaction_id: TransactionId
) -> list[Attachment]:
    t = _visible_transaction(uow, actor, transaction_id)
    return uow.attachments.for_transactions(actor.household_id, [t.id]).get(t.id, [])


def add_attachment(
    uow: UnitOfWork,
    store: AttachmentStore,
    actor: Actor,
    transaction_id: TransactionId,
    filename: str,
    content: bytes,
    now: datetime,
) -> AttachmentResult:
    t = _visible_transaction(uow, actor, transaction_id)
    try:
        content_type, extension = validate(content)
    except AttachmentError as exc:
        raise InvalidRequestError(str(exc)) from exc
    existing = uow.attachments.for_transactions(actor.household_id, [t.id]).get(t.id, [])
    if len(existing) >= MAX_PER_TRANSACTION:
        raise InvalidRequestError(
            f"Un movimiento admite como máximo {MAX_PER_TRANSACTION} adjuntos"
        )
    attachment = Attachment(
        id=uuid4(),
        household_id=actor.household_id,
        transaction_id=t.id,
        filename=clean_filename(filename, extension),
        content_type=content_type,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        created_by=actor.user_id,
        created_at=now,
    )
    # Primero el archivo y después la fila: si algo falla, sobra un archivo, nunca falta.
    store.save(attachment.id, content)
    try:
        uow.attachments.add(attachment)
        operation = change_log.record(
            uow,
            actor,
            "attachment.add",
            f"Adjunto «{attachment.filename}» en «{t.description}»",
            [Change(Entity.ATTACHMENT, str(attachment.id), "present", None, True)],
            now,
        )
        uow.commit()
    except BaseException:
        store.delete(attachment.id)
        raise
    return AttachmentResult(attachment, operation.id if operation else None)


def get_attachment(
    uow: UnitOfWork, store: AttachmentStore, actor: Actor, attachment_id: UUID
) -> tuple[Attachment, bytes]:
    """El adjunto y su contenido, si quien pregunta ve su movimiento."""
    attachment = uow.attachments.get(actor.household_id, attachment_id)
    if attachment is None or attachment.is_deleted:
        raise NotFoundError("Adjunto no encontrado")
    _visible_transaction(uow, actor, attachment.transaction_id)
    content = store.read(attachment.id)
    if content is None:
        raise NotFoundError("Adjunto no encontrado")
    return attachment, content


def delete_attachment(
    uow: UnitOfWork, actor: Actor, attachment_id: UUID, now: datetime
) -> AttachmentResult:
    attachment = uow.attachments.get(actor.household_id, attachment_id)
    if attachment is None or attachment.is_deleted:
        raise NotFoundError("Adjunto no encontrado")
    t = _visible_transaction(uow, actor, attachment.transaction_id)
    uow.attachments.set_deleted(actor.household_id, attachment.id, now)
    operation = change_log.record(
        uow,
        actor,
        "attachment.delete",
        f"Adjunto «{attachment.filename}» borrado de «{t.description}»",
        [Change(Entity.ATTACHMENT, str(attachment.id), "present", True, False)],
        now,
    )
    uow.commit()
    return AttachmentResult(attachment, operation.id if operation else None)


def purge_deleted(uow: UnitOfWork, store: AttachmentStore, now: datetime) -> int:
    """Borra del disco y de la base de datos los adjuntos borrados hace más de 30 días."""
    old = uow.attachments.deleted_before(now - KEEP_DELETED)
    for attachment in old:
        store.delete(attachment.id)
        uow.attachments.erase(attachment.id)
    uow.commit()
    return len(old)
