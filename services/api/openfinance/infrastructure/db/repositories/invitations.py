"""Repositorio de invitaciones al hogar (ADR-0026, OF-1601)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from openfinance.domain.shared.ids import UserId, WorkspaceId
from openfinance.domain.workspaces import Invitation, Role
from openfinance.infrastructure.db.models import InvitationRow
from openfinance.infrastructure.db.repositories._common import _as_utc, _flush


def _domain(row: InvitationRow) -> Invitation:
    return Invitation(
        id=row.id,
        household_id=WorkspaceId(row.household_id),
        created_by=UserId(row.created_by),
        role=Role(row.role),
        token_hash=row.token_hash,
        created_at=_as_utc(row.created_at),
        expires_at=_as_utc(row.expires_at),
        accepted_at=_as_utc(row.accepted_at) if row.accepted_at else None,
        revoked=row.revoked,
    )


class SqlInvitationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, invitation: Invitation) -> None:
        self._s.add(
            InvitationRow(
                id=invitation.id,
                household_id=invitation.household_id,
                created_by=invitation.created_by,
                role=invitation.role.value,
                token_hash=invitation.token_hash,
                created_at=invitation.created_at,
                expires_at=invitation.expires_at,
            )
        )
        _flush(self._s)

    def get(self, household_id: WorkspaceId, invitation_id: UUID) -> Invitation | None:
        row = self._s.scalar(
            select(InvitationRow).where(
                InvitationRow.household_id == household_id, InvitationRow.id == invitation_id
            )
        )
        return _domain(row) if row else None

    def by_token_hash(self, token_hash: str) -> Invitation | None:
        row = self._s.scalar(select(InvitationRow).where(InvitationRow.token_hash == token_hash))
        return _domain(row) if row else None

    def for_household(self, household_id: WorkspaceId) -> list[Invitation]:
        rows = self._s.scalars(
            select(InvitationRow)
            .where(InvitationRow.household_id == household_id)
            .order_by(InvitationRow.created_at.desc(), InvitationRow.id)
        )
        return [_domain(r) for r in rows]

    def save(self, invitation: Invitation) -> None:
        row = self._s.get(InvitationRow, invitation.id)
        if row is None:
            raise LookupError(invitation.id)
        row.accepted_at = invitation.accepted_at
        row.revoked = invitation.revoked
        _flush(self._s)
