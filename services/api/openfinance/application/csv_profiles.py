"""Perfiles de CSV: crear, cambiar, borrar y probar (ADR-0020, OF-1105).

Un perfil es del hogar (describe el formato de un banco, no datos de nadie). Probarlo lee un
archivo con el perfil y enseña las primeras filas sin guardar nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from openfinance.application import changes as change_log
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ports import StatementParsers, UnitOfWork
from openfinance.domain.changes import Change, Entity
from openfinance.domain.csv_profile import CsvProfile, CsvSample, ProfileError, build
from openfinance.domain.imports import ClassificationRules, ImportedRow, SkippedRow
from openfinance.domain.imports.batch import MAX_FILE_BYTES
from openfinance.domain.workspaces import Actor

MAX_PROFILES = 50
TEST_ROWS = 20


def list_profiles(uow: UnitOfWork, actor: Actor) -> list[CsvProfile]:
    return uow.csv_profiles.for_household(actor.household_id)


def _check_name(uow: UnitOfWork, actor: Actor, name: str, own_id: UUID | None) -> None:
    wanted = " ".join(name.split()).casefold()
    if any(p.name.casefold() == wanted and p.id != own_id for p in list_profiles(uow, actor)):
        raise ConflictError("Ya hay un perfil con ese nombre")


def _build(actor: Actor, profile_id: UUID, name: str, config: dict[str, Any]) -> CsvProfile:
    try:
        return build(profile_id, actor.household_id, name, config)
    except ProfileError as exc:
        raise InvalidRequestError(str(exc)) from exc


def create_profile(
    uow: UnitOfWork, actor: Actor, name: str, config: dict[str, Any], now: datetime
) -> tuple[CsvProfile, UUID | None]:
    if len(list_profiles(uow, actor)) >= MAX_PROFILES:
        raise ConflictError(f"El hogar ya tiene {MAX_PROFILES} perfiles")
    _check_name(uow, actor, name, None)
    profile = _build(actor, uuid4(), name, config)
    uow.csv_profiles.save(profile, actor.user_id)
    operation = change_log.record(
        uow,
        actor,
        "csv_profile.create",
        f"Perfil de CSV «{profile.name}» creado",
        [Change(Entity.CSV_PROFILE, str(profile.id), "definition", None, profile.definition())],
        now,
    )
    uow.commit()
    return profile, operation.id if operation else None


def update_profile(
    uow: UnitOfWork,
    actor: Actor,
    profile_id: UUID,
    name: str,
    config: dict[str, Any],
    now: datetime,
) -> tuple[CsvProfile, UUID | None]:
    before = uow.csv_profiles.get(actor.household_id, profile_id)
    if before is None:
        raise NotFoundError("Perfil no encontrado")
    _check_name(uow, actor, name, profile_id)
    profile = _build(actor, profile_id, name, config)
    if profile.definition() == before.definition():
        return before, None
    uow.csv_profiles.save(profile, actor.user_id)
    operation = change_log.record(
        uow,
        actor,
        "csv_profile.update",
        f"Perfil de CSV «{profile.name}» cambiado",
        [
            Change(
                Entity.CSV_PROFILE,
                str(profile_id),
                "definition",
                before.definition(),
                profile.definition(),
            )
        ],
        now,
    )
    uow.commit()
    return profile, operation.id if operation else None


def delete_profile(uow: UnitOfWork, actor: Actor, profile_id: UUID, now: datetime) -> UUID | None:
    profile = uow.csv_profiles.get(actor.household_id, profile_id)
    if profile is None:
        raise NotFoundError("Perfil no encontrado")
    uow.csv_profiles.delete(actor.household_id, profile_id)
    operation = change_log.record(
        uow,
        actor,
        "csv_profile.delete",
        f"Perfil de CSV «{profile.name}» borrado",
        [Change(Entity.CSV_PROFILE, str(profile_id), "definition", profile.definition(), None)],
        now,
    )
    uow.commit()
    return operation.id if operation else None


def _read(content: bytes) -> bytes:
    if not content:
        raise InvalidRequestError("El archivo está vacío")
    if len(content) > MAX_FILE_BYTES:
        raise InvalidRequestError("El archivo es demasiado grande (máximo 5 MB)")
    return content


def sample_file(parsers: StatementParsers, content: bytes) -> CsvSample:
    """Las primeras filas del archivo y un separador y una codificación propuestos."""
    return parsers.csv_sample(_read(content))


@dataclass(frozen=True, slots=True)
class ProfileTest:
    rows: list[ImportedRow]
    """Las primeras filas leídas con el perfil."""
    total: int
    skipped: list[SkippedRow]
    skipped_total: int


def test_profile(
    uow: UnitOfWork,
    parsers: StatementParsers,
    actor: Actor,
    name: str,
    config: dict[str, Any],
    content: bytes,
) -> ProfileTest:
    """Lee el archivo con un perfil (guardado o no) sin guardar nada."""
    profile = _build(actor, uuid4(), name or "prueba", config)
    household = uow.households.get(actor.household_id)
    currency = household.currency.code if household else "EUR"
    try:
        result = parsers.csv(profile)(
            _read(content), "prueba", ClassificationRules(currency=currency)
        )
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    return ProfileTest(
        result.rows[:TEST_ROWS], len(result.rows), result.skipped[:TEST_ROWS], len(result.skipped)
    )
