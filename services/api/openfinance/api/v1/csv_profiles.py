"""Perfiles de CSV para importar el extracto de cualquier banco (ADR-0020, OF-1105)."""

import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from openfinance.api.deps import ActorDep, ParsersDep, UowDep
from openfinance.api.v1.schemas import (
    CsvProfileChangeOut,
    CsvProfileIn,
    CsvProfileOut,
    CsvSampleOut,
    CsvTestOut,
    CsvTestRowOut,
    MoneyOut,
    OperationRefOut,
    SkippedRowOut,
)
from openfinance.application import csv_profiles
from openfinance.application.errors import InvalidRequestError
from openfinance.domain.imports.batch import MAX_FILE_BYTES
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["imports"])


def _config(body: CsvProfileIn) -> dict[str, Any]:
    return body.model_dump(exclude={"name"})


@router.get("/csv-profiles", response_model=list[CsvProfileOut])
def list_profiles(actor: ActorDep, uow: UowDep) -> list[CsvProfileOut]:
    return [CsvProfileOut.of(p) for p in csv_profiles.list_profiles(uow, actor)]


@router.post(
    "/csv-profiles", response_model=CsvProfileChangeOut, status_code=status.HTTP_201_CREATED
)
def create_profile(body: CsvProfileIn, actor: ActorDep, uow: UowDep) -> CsvProfileChangeOut:
    profile, operation_id = csv_profiles.create_profile(
        uow, actor, body.name, _config(body), utc_now()
    )
    return CsvProfileChangeOut(profile=CsvProfileOut.of(profile), operation_id=operation_id)


@router.put("/csv-profiles/{profile_id}", response_model=CsvProfileChangeOut)
def update_profile(
    profile_id: UUID, body: CsvProfileIn, actor: ActorDep, uow: UowDep
) -> CsvProfileChangeOut:
    profile, operation_id = csv_profiles.update_profile(
        uow, actor, profile_id, body.name, _config(body), utc_now()
    )
    return CsvProfileChangeOut(profile=CsvProfileOut.of(profile), operation_id=operation_id)


@router.delete("/csv-profiles/{profile_id}", response_model=OperationRefOut)
def delete_profile(profile_id: UUID, actor: ActorDep, uow: UowDep) -> OperationRefOut:
    return OperationRefOut(
        operation_id=csv_profiles.delete_profile(uow, actor, profile_id, utc_now())
    )


@router.post("/csv-profiles/sample", response_model=CsvSampleOut)
async def sample(
    parsers: ParsersDep,
    actor: ActorDep,
    file: Annotated[UploadFile, File(description="El CSV del banco")],
) -> CsvSampleOut:
    """Las primeras filas del archivo y un separador y una codificación propuestos. No guarda."""
    content = await file.read(MAX_FILE_BYTES + 1)
    found = await run_in_threadpool(csv_profiles.sample_file, parsers, content)
    return CsvSampleOut(delimiter=found.delimiter, encoding=found.encoding, rows=found.rows)


@router.post("/csv-profiles/test", response_model=CsvTestOut)
async def test_profile(
    uow: UowDep,
    parsers: ParsersDep,
    actor: ActorDep,
    file: Annotated[UploadFile, File(description="El CSV del banco")],
    profile: Annotated[str, Form(description="El perfil a probar, en JSON")],
) -> CsvTestOut:
    """Lee el archivo con un perfil (sin guardarlo) y enseña las primeras filas. No guarda."""
    try:
        body = CsvProfileIn.model_validate(json.loads(profile))
    except (ValueError, ValidationError) as exc:
        raise InvalidRequestError("El perfil no es válido") from exc
    content = await file.read(MAX_FILE_BYTES + 1)
    result = await run_in_threadpool(
        csv_profiles.test_profile, uow, parsers, actor, body.name, _config(body), content
    )
    return CsvTestOut(
        rows=[
            CsvTestRowOut(
                line=r.line,
                booked_at=r.booked_at,
                description=r.description,
                amount=MoneyOut.of(r.amount),
                balance=MoneyOut.of(r.balance_after) if r.balance_after else None,
            )
            for r in result.rows
        ],
        total=result.total,
        skipped=[
            SkippedRowOut(line=s.line, reason=s.reason, description=s.description)
            for s in result.skipped
        ],
        skipped_total=result.skipped_total,
    )
