"""Personas del hogar: roles, invitaciones y bajas (ADR-0026, OF-1601).

El rol decide qué puede hacer una persona, no qué ve: una cuenta personal sigue siendo solo de
su titular aunque quien mire sea ``owner`` (ADR-0013).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from openfinance.application.errors import (
    ConflictError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
)
from openfinance.application.identity import NewSession, open_session
from openfinance.application.ports import PasswordHasher, UnitOfWork
from openfinance.domain.identity import InvalidUserError, User, normalize_email, validate_password
from openfinance.domain.ledger import AccountKind
from openfinance.domain.shared.ids import UserId
from openfinance.domain.workspaces import (
    INVITATION_TTL,
    MAX_MEMBERS,
    MAX_PENDING_INVITATIONS,
    Actor,
    Invitation,
    Role,
)

INVALID_INVITATION = "La invitación no es válida o ha caducado"
"""Un único mensaje para todo fallo: no se distingue entre inexistente, usada o caducada."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_owner(actor: Actor) -> None:
    if not actor.role.can_manage:
        raise ForbiddenError("Solo quien administra el hogar puede hacer esto")


@dataclass(frozen=True, slots=True)
class MemberView:
    user: User
    role: Role


def list_members(uow: UnitOfWork, actor: Actor) -> list[MemberView]:
    roles = uow.households.roles(actor.household_id)
    return [
        MemberView(u, roles.get(u.id, Role.VIEWER))
        for u in uow.households.members(actor.household_id)
    ]


def create_invitation(
    uow: UnitOfWork, actor: Actor, role: Role, now: datetime
) -> tuple[Invitation, str]:
    """Crea la invitación y devuelve el enlace en claro **una sola vez**."""
    require_owner(actor)
    if len(uow.households.members(actor.household_id)) >= MAX_MEMBERS:
        raise ConflictError(f"Un hogar admite como mucho {MAX_MEMBERS} personas")
    pending = [i for i in uow.invitations.for_household(actor.household_id) if i.is_pending(now)]
    if len(pending) >= MAX_PENDING_INVITATIONS:
        raise ConflictError("Hay demasiadas invitaciones pendientes; revoca alguna")
    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        id=uuid4(),
        household_id=actor.household_id,
        created_by=actor.user_id,
        role=role,
        token_hash=_hash(token),
        created_at=now,
        expires_at=now + INVITATION_TTL,
    )
    uow.invitations.add(invitation)
    uow.commit()
    return invitation, token


def list_invitations(uow: UnitOfWork, actor: Actor, now: datetime) -> list[Invitation]:
    """Las pendientes del hogar (nunca el enlace: no se puede recuperar)."""
    require_owner(actor)
    return [i for i in uow.invitations.for_household(actor.household_id) if i.is_pending(now)]


def revoke_invitation(uow: UnitOfWork, actor: Actor, invitation_id: UUID) -> None:
    require_owner(actor)
    invitation = uow.invitations.get(actor.household_id, invitation_id)
    if invitation is None:
        raise NotFoundError("Invitación no encontrada")
    uow.invitations.save(replace(invitation, revoked=True))
    uow.commit()


def accept_invitation(
    uow: UnitOfWork,
    hasher: PasswordHasher,
    token: str,
    display_name: str,
    email: str,
    password: str,
    now: datetime,
    ttl: timedelta,
) -> NewSession:
    """Crea a la persona, la une al hogar con el rol de la invitación y abre su sesión."""
    invitation = uow.invitations.by_token_hash(_hash(token))
    if invitation is None or not invitation.is_pending(now):
        raise InvalidRequestError(INVALID_INVITATION)
    try:
        normalized = normalize_email(email)
        validate_password(password)
        name = " ".join(display_name.split())
        if not name or len(name) > 100:
            raise InvalidUserError("El nombre va de 1 a 100 caracteres")
        user = User(UserId(uuid4()), normalized, name, hasher.hash(password))
    except InvalidUserError as exc:
        raise InvalidRequestError(str(exc)) from exc
    if len(uow.households.members(invitation.household_id)) >= MAX_MEMBERS:
        raise ConflictError(f"Un hogar admite como mucho {MAX_MEMBERS} personas")
    if uow.users.get_by_email(normalized) is not None:
        raise ConflictError("Ese email ya tiene una cuenta")
    uow.users.add(user)
    uow.households.add_member(invitation.household_id, user.id, invitation.role)
    uow.invitations.save(replace(invitation, accepted_at=now))
    return open_session(uow, user, now, ttl)


def _owners(uow: UnitOfWork, actor: Actor) -> list[UserId]:
    return [u for u, r in uow.households.roles(actor.household_id).items() if r is Role.OWNER]


def set_role(uow: UnitOfWork, actor: Actor, user_id: UserId, role: Role) -> None:
    require_owner(actor)
    current = uow.households.role_of(actor.household_id, user_id)
    if current is None:
        raise NotFoundError("Persona no encontrada")
    if current is Role.OWNER and role is not Role.OWNER and _owners(uow, actor) == [user_id]:
        raise InvalidRequestError("El hogar no puede quedarse sin quien lo administre")
    uow.households.set_role(actor.household_id, user_id, role)
    uow.commit()


def remove_member(uow: UnitOfWork, actor: Actor, user_id: UserId) -> None:
    """Quita a alguien del hogar y cierra sus sesiones. No borra nada de lo que anotó."""
    require_owner(actor)
    role = uow.households.role_of(actor.household_id, user_id)
    if role is None:
        raise NotFoundError("Persona no encontrada")
    if user_id == actor.user_id:
        raise InvalidRequestError("No puedes quitarte a ti mismo")
    if role is Role.OWNER and _owners(uow, actor) == [user_id]:
        raise InvalidRequestError("El hogar no puede quedarse sin quien lo administre")
    has_personal = any(
        a.kind is AccountKind.PERSONAL and a.owner_id == user_id
        for a in uow.accounts.for_household(actor.household_id)
    )
    if has_personal:
        raise InvalidRequestError(
            "Esa persona tiene cuentas personales: sus movimientos no se pueden dejar sin dueño"
        )
    uow.households.remove_member(actor.household_id, user_id)
    uow.sessions.delete_for_user(user_id)
    uow.commit()
