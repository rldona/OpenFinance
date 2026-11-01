from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from openfinance.api.deps import ActorDep, ParsersDep, UowDep
from openfinance.api.v1.schemas import ImportPreviewOut, ImportResultOut
from openfinance.application import imports
from openfinance.application.errors import InvalidRequestError
from openfinance.domain.imports.batch import MAX_FILE_BYTES
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["imports"])


@router.post("/imports", response_model=ImportPreviewOut, status_code=201)
async def create_import(
    actor: ActorDep,
    uow: UowDep,
    parsers: ParsersDep,
    account_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File(description="Extracto del banco (CSV o XLSX)")],
) -> ImportPreviewOut:
    """Lee el extracto y devuelve la vista previa. No guarda movimientos."""
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise InvalidRequestError("El archivo es demasiado grande (máximo 5 MB)")
    # Leer el extracto es trabajo de CPU y de base de datos síncrono: fuera del bucle.
    preview = await run_in_threadpool(
        imports.preview_import,
        uow,
        parsers,
        actor,
        account_id,
        file.filename or "extracto",
        content,
        utc_now(),
    )
    return ImportPreviewOut.of(preview)


@router.post("/imports/{import_id}/commit", response_model=ImportResultOut)
def commit_import(
    import_id: UUID, actor: ActorDep, uow: UowDep, parsers: ParsersDep
) -> ImportResultOut:
    """Guarda los movimientos nuevos. Repetir la llamada no vuelve a guardarlos."""
    return ImportResultOut.of(imports.commit_import(uow, parsers, actor, import_id, utc_now()))
