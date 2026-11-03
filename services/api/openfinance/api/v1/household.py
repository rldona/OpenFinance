"""Personas del hogar: roles e invitaciones (ADR-0026, OF-1601)."""

from uuid import UUID

from fastapi import APIRouter, Response, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    InvitationCreatedOut,
    InvitationIn,
    InvitationOut,
    MemberDetailOut,
    RoleIn,
)
from openfinance.application import members
from openfinance.domain.shared.ids import UserId
from openfinance.domain.workspaces import Invitation, Role
from openfinance.infrastructure.time import utc_now

router = APIRouter(prefix="/household", tags=["household"])


def _invitation(i: Invitation) -> InvitationOut:
    return InvitationOut(
        id=i.id, role=i.role.value, created_at=i.created_at, expires_at=i.expires_at
    )


@router.get("/members", response_model=list[MemberDetailOut])
def list_members(actor: ActorDep, uow: UowDep) -> list[MemberDetailOut]:
    return [
        MemberDetailOut(
            id=m.user.id,
            display_name=m.user.display_name,
            role=m.role.value,
            is_me=m.user.id == actor.user_id,
        )
        for m in members.list_members(uow, actor)
    ]


@router.put("/members/{user_id}/role", status_code=status.HTTP_204_NO_CONTENT)
def set_role(user_id: UUID, body: RoleIn, actor: ActorDep, uow: UowDep) -> Response:
    members.set_role(uow, actor, UserId(user_id), Role(body.role))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(user_id: UUID, actor: ActorDep, uow: UowDep) -> Response:
    members.remove_member(uow, actor, UserId(user_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(actor: ActorDep, uow: UowDep) -> list[InvitationOut]:
    return [_invitation(i) for i in members.list_invitations(uow, actor, utc_now())]


@router.post(
    "/invitations", response_model=InvitationCreatedOut, status_code=status.HTTP_201_CREATED
)
def create_invitation(body: InvitationIn, actor: ActorDep, uow: UowDep) -> InvitationCreatedOut:
    invitation, token = members.create_invitation(uow, actor, Role(body.role), utc_now())
    return InvitationCreatedOut(invitation=_invitation(invitation), token=token)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(invitation_id: UUID, actor: ActorDep, uow: UowDep) -> Response:
    members.revoke_invitation(uow, actor, invitation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
