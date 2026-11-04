"""Adjuntos de movimientos: tickets y facturas (OF-1007)."""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from openfinance.api.deps import ActorDep, AttachmentStoreDep, UowDep
from openfinance.api.v1.schemas import AttachmentAddedOut, AttachmentOut, OperationRefOut
from openfinance.application import attachments
from openfinance.application.errors import InvalidRequestError
from openfinance.domain.attachments import MAX_BYTES
from openfinance.domain.shared.ids import TransactionId
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["attachments"])


@router.get("/transactions/{transaction_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(transaction_id: UUID, actor: ActorDep, uow: UowDep) -> list[AttachmentOut]:
    found = attachments.list_attachments(uow, actor, TransactionId(transaction_id))
    return [AttachmentOut.of(a) for a in found]


@router.post(
    "/transactions/{transaction_id}/attachments",
    response_model=AttachmentAddedOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_attachment(
    transaction_id: UUID,
    actor: ActorDep,
    uow: UowDep,
    store: AttachmentStoreDep,
    file: Annotated[UploadFile, File(description="PDF o imagen PNG, JPEG o WebP (máx. 5 MB)")],
) -> AttachmentAddedOut:
    """Adjunta un ticket o una factura al movimiento; se puede deshacer."""
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise InvalidRequestError("El archivo es demasiado grande (máximo 5 MB)")
    result = await run_in_threadpool(
        attachments.add_attachment,
        uow,
        store,
        actor,
        TransactionId(transaction_id),
        file.filename or "adjunto",
        content,
        utc_now(),
    )
    return AttachmentAddedOut(
        attachment=AttachmentOut.of(result.attachment), operation_id=result.operation_id
    )


@router.get("/attachments/{attachment_id}")
def download_attachment(
    attachment_id: UUID, actor: ActorDep, uow: UowDep, store: AttachmentStoreDep
) -> Response:
    """Descarga el archivo. Siempre como descarga, nunca para abrirlo dentro de la página."""
    attachment, content = attachments.get_attachment(uow, store, actor, attachment_id)
    return Response(
        content,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.delete("/attachments/{attachment_id}", response_model=OperationRefOut)
def delete_attachment(attachment_id: UUID, actor: ActorDep, uow: UowDep) -> OperationRefOut:
    """Borra el adjunto. El archivo se conserva 30 días por si se deshace."""
    result = attachments.delete_attachment(uow, actor, attachment_id, utc_now())
    return OperationRefOut(operation_id=result.operation_id)
