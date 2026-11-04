"""Patrones por persona: textos del banco que identifican sus aportaciones (ADR-0015).

Se gestionan desde la línea de comandos del servidor; no se exponen por la API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from openfinance.application.errors import InvalidRequestError, NotFoundError
from openfinance.application.ports import UnitOfWork
from openfinance.domain.identity import InvalidUserError, User, normalize_email
from openfinance.domain.imports import (
    MemberPattern,
    PatternDirection,
    PatternError,
    normalize_member_pattern,
)
from openfinance.domain.shared.ids import UserId, WorkspaceId
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class ListedPattern:
    pattern: MemberPattern
    member: User


def _member(uow: UnitOfWork, email: str) -> tuple[User, WorkspaceId]:
    try:
        normalized = normalize_email(email)
    except InvalidUserError as exc:
        raise InvalidRequestError(str(exc)) from exc
    user = uow.users.get_by_email(normalized)
    if user is None:
        raise NotFoundError(f"No hay ninguna persona con el email {normalized}")
    households = uow.households.households_of(user.id)
    if len(households) != 1:
        raise InvalidRequestError(
            f"{normalized} pertenece a {len(households)} hogares; se esperaba exactamente uno"
        )
    return user, households[0]


def _normalize(raw: str) -> str:
    try:
        return normalize_member_pattern(raw)
    except PatternError as exc:
        raise InvalidRequestError(str(exc)) from exc


def add_member_pattern(
    uow: UnitOfWork, email: str, raw: str, direction: PatternDirection, now: datetime
) -> MemberPattern:
    user, household = _member(uow, email)
    pattern = MemberPattern(household, user.id, _normalize(raw), direction)
    uow.member_patterns.add(pattern, now)
    uow.commit()
    return pattern


def list_member_patterns(uow: UnitOfWork, email: str) -> list[ListedPattern]:
    """Los patrones de todo el hogar de esa persona, con quién aporta en cada uno."""
    _, household = _member(uow, email)
    members = {m.id: m for m in uow.households.members(household)}
    return [
        ListedPattern(p, members[p.user_id])
        for p in uow.member_patterns.for_household(household)
        if p.user_id in members
    ]


def remove_member_pattern(
    uow: UnitOfWork, email: str, raw: str, direction: PatternDirection
) -> None:
    user, household = _member(uow, email)
    pattern = _normalize(raw)
    owned = any(
        p.user_id == user.id and p.direction is direction and p.pattern == pattern
        for p in uow.member_patterns.for_household(household)
    )
    if not owned or not uow.member_patterns.delete(household, direction, pattern):
        raise NotFoundError("Esa persona no tiene ese patrón")
    uow.commit()


# Desde la web (OF-704): cada persona gestiona solo los suyos, sin pasar por el email.


def own_patterns(uow: UnitOfWork, actor: Actor) -> list[MemberPattern]:
    return [
        p
        for p in uow.member_patterns.for_household(actor.household_id)
        if p.user_id == actor.user_id
    ]


def add_own_pattern(
    uow: UnitOfWork, actor: Actor, raw: str, direction: PatternDirection, now: datetime
) -> MemberPattern:
    pattern = MemberPattern(actor.household_id, actor.user_id, _normalize(raw), direction)
    uow.member_patterns.add(pattern, now)
    uow.commit()
    return pattern


def remove_own_pattern(
    uow: UnitOfWork, actor: Actor, raw: str, direction: PatternDirection
) -> None:
    pattern = _normalize(raw)
    owned = any(p.pattern == pattern and p.direction is direction for p in own_patterns(uow, actor))
    if not owned or not uow.member_patterns.delete(actor.household_id, direction, pattern):
        raise NotFoundError("No tienes ese patrón")
    uow.commit()


def members_without_recharge(uow: UnitOfWork, household_id: WorkspaceId) -> list[UserId]:
    """Personas del hogar sin patrón de entrada: sus recargas a la conjunta entrarían como
    ingreso («Recarga de *NNNN» no lleva su nombre)."""
    with_pattern = {
        p.user_id
        for p in uow.member_patterns.for_household(household_id)
        if p.direction is PatternDirection.INFLOW
    }
    return [m.id for m in uow.households.members(household_id) if m.id not in with_pattern]
