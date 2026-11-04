"""Repositorios de personas, hogares y sesiones."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from openfinance.application.ports import StoredSession
from openfinance.domain.identity import User
from openfinance.domain.shared import Currency
from openfinance.domain.shared.ids import (
    UserId,
    WorkspaceId,
)
from openfinance.domain.workspaces import Household, Role
from openfinance.infrastructure.db.models import (
    HouseholdRow,
    MembershipRow,
    SessionRow,
    UserRow,
)
from openfinance.infrastructure.db.repositories._common import (
    _as_utc,
)


def _user(row: UserRow) -> User:
    return User(UserId(row.id), row.email, row.display_name, row.password_hash)


class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, user_id: UserId) -> User | None:
        row = self._s.get(UserRow, user_id)
        return _user(row) if row else None

    def get_by_email(self, email: str) -> User | None:
        row = self._s.scalar(select(UserRow).where(UserRow.email == email))
        return _user(row) if row else None

    def add(self, user: User) -> None:
        self._s.add(
            UserRow(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                password_hash=user.password_hash,
            )
        )
        self._s.flush()

    def set_password_hash(self, user_id: UserId, password_hash: str) -> None:
        self._s.execute(
            update(UserRow).where(UserRow.id == user_id).values(password_hash=password_hash)
        )


class SqlHouseholdRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, household_id: WorkspaceId) -> Household | None:
        row = self._s.get(HouseholdRow, household_id)
        return Household(WorkspaceId(row.id), row.name, Currency(row.currency)) if row else None

    def add(self, household: Household) -> None:
        self._s.add(
            HouseholdRow(id=household.id, name=household.name, currency=household.currency.code)
        )
        self._s.flush()

    def add_member(
        self, household_id: WorkspaceId, user_id: UserId, role: Role = Role.OWNER
    ) -> None:
        self._s.add(MembershipRow(household_id=household_id, user_id=user_id, role=role.value))
        self._s.flush()

    def roles(self, household_id: WorkspaceId) -> dict[UserId, Role]:
        rows = self._s.execute(
            select(MembershipRow.user_id, MembershipRow.role).where(
                MembershipRow.household_id == household_id
            )
        )
        return {UserId(u): Role(r) for u, r in rows}

    def role_of(self, household_id: WorkspaceId, user_id: UserId) -> Role | None:
        role = self._s.scalar(
            select(MembershipRow.role).where(
                MembershipRow.household_id == household_id, MembershipRow.user_id == user_id
            )
        )
        return Role(role) if role else None

    def set_role(self, household_id: WorkspaceId, user_id: UserId, role: Role) -> None:
        self._s.execute(
            update(MembershipRow)
            .where(MembershipRow.household_id == household_id, MembershipRow.user_id == user_id)
            .values(role=role.value)
        )
        self._s.flush()

    def remove_member(self, household_id: WorkspaceId, user_id: UserId) -> None:
        self._s.execute(
            delete(MembershipRow).where(
                MembershipRow.household_id == household_id, MembershipRow.user_id == user_id
            )
        )
        self._s.flush()

    def households_of(self, user_id: UserId) -> list[WorkspaceId]:
        rows = self._s.scalars(
            select(MembershipRow.household_id)
            .where(MembershipRow.user_id == user_id)
            .order_by(MembershipRow.created_at)
        )
        return [WorkspaceId(h) for h in rows]

    def all_ids(self) -> list[WorkspaceId]:
        return [WorkspaceId(h) for h in self._s.scalars(select(HouseholdRow.id))]

    def members(self, household_id: WorkspaceId) -> list[User]:
        rows = self._s.scalars(
            select(UserRow)
            .join(MembershipRow, MembershipRow.user_id == UserRow.id)
            .where(MembershipRow.household_id == household_id)
            .order_by(UserRow.display_name)
        )
        return [_user(r) for r in rows]


class SqlSessionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, session: StoredSession) -> None:
        self._s.add(
            SessionRow(
                token_hash=session.token_hash,
                user_id=session.user_id,
                household_id=session.household_id,
                expires_at=session.expires_at,
            )
        )
        self._s.flush()

    def get(self, token_hash: str) -> StoredSession | None:
        row = self._s.get(SessionRow, token_hash)
        if row is None:
            return None
        return StoredSession(
            row.token_hash,
            UserId(row.user_id),
            WorkspaceId(row.household_id),
            _as_utc(row.expires_at),
        )

    def delete(self, token_hash: str) -> None:
        self._s.execute(delete(SessionRow).where(SessionRow.token_hash == token_hash))

    def delete_expired(self, now: datetime) -> int:
        result = self._s.execute(delete(SessionRow).where(SessionRow.expires_at <= now))
        return int(getattr(result, "rowcount", 0) or 0)

    def delete_for_user(self, user_id: UserId, *, keep: str | None = None) -> int:
        stmt = delete(SessionRow).where(SessionRow.user_id == user_id)
        if keep is not None:
            stmt = stmt.where(SessionRow.token_hash != keep)
        result = self._s.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    def delete_all(self) -> int:
        result = self._s.execute(delete(SessionRow))
        return int(getattr(result, "rowcount", 0) or 0)
