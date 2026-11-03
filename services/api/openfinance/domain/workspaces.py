"""El hogar (workspace) y quién pertenece a él."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from openfinance.domain.shared import Currency
from openfinance.domain.shared.ids import UserId, WorkspaceId

MAX_MEMBERS = 10
MAX_PENDING_INVITATIONS = 10
INVITATION_TTL = timedelta(days=7)


class Role(StrEnum):
    """Qué puede hacer una persona en el hogar (ADR-0002, ADR-0026). No abre cuentas personales."""

    OWNER = "owner"
    """Todo, y además invita, cambia roles y quita personas."""
    EDITOR = "editor"
    """Escribe datos del hogar; no gestiona personas."""
    VIEWER = "viewer"
    """Solo lee."""

    @property
    def can_write(self) -> bool:
        return self is not Role.VIEWER

    @property
    def can_manage(self) -> bool:
        return self is Role.OWNER


@dataclass(frozen=True, slots=True)
class Household:
    id: WorkspaceId
    name: str
    currency: Currency

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("El hogar necesita un nombre")


@dataclass(frozen=True, slots=True)
class Actor:
    """Quién hace la petición y en qué hogar. Toda lectura y escritura parte de aquí."""

    user_id: UserId
    household_id: WorkspaceId
    role: Role = Role.OWNER
    """Por defecto ``owner``: lo que ya existía no cambia; la API aplica el rol real."""


class InvitationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Invitation:
    """Una invitación para unirse al hogar. El enlace no se guarda: solo su hash."""

    id: UUID
    household_id: WorkspaceId
    created_by: UserId
    role: Role
    token_hash: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked: bool = False

    def is_pending(self, now: datetime) -> bool:
        return self.accepted_at is None and not self.revoked and now < self.expires_at
