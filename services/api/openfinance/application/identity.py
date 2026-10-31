"""Inicio de sesión y sesiones (OF-101)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from openfinance.application.errors import AuthenticationError, NotFoundError
from openfinance.application.ports import PasswordHasher, StoredSession, UnitOfWork
from openfinance.domain.identity import InvalidUserError, User, normalize_email
from openfinance.domain.workspaces import Actor, Household


@dataclass(frozen=True, slots=True)
class NewSession:
    token: str
    """Valor para la cookie. Solo se guarda su hash."""
    expires_at: datetime
    actor: Actor


@dataclass(frozen=True, slots=True)
class Me:
    user: User
    household: Household
    members: list[User]


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login(
    uow: UnitOfWork,
    hasher: PasswordHasher,
    email: str,
    password: str,
    now: datetime,
    ttl: timedelta,
    previous_token: str = "",
) -> NewSession:
    """Inicia sesión. Sustituye la sesión que traiga el navegador y purga las caducadas."""
    try:
        user = uow.users.get_by_email(normalize_email(email))
    except InvalidUserError:
        user = None
    if user is None:
        hasher.dummy_verify(password)
        raise AuthenticationError
    if not hasher.verify(user.password_hash, password):
        raise AuthenticationError
    households = uow.households.households_of(user.id)
    if not households:
        raise AuthenticationError
    if previous_token:
        uow.sessions.delete(_hash_token(previous_token))
    uow.sessions.delete_expired(now)
    token = secrets.token_urlsafe(32)
    session = StoredSession(_hash_token(token), user.id, households[0], now + ttl)
    uow.sessions.add(session)
    uow.commit()
    return NewSession(token, session.expires_at, Actor(user.id, session.household_id))


def resolve_session(uow: UnitOfWork, token: str, now: datetime) -> Actor | None:
    if not token:
        return None
    session = uow.sessions.get(_hash_token(token))
    if session is None:
        return None
    if session.expires_at <= now:
        uow.sessions.delete(session.token_hash)
        uow.commit()
        return None
    if session.household_id not in uow.households.households_of(session.user_id):
        return None
    return Actor(session.user_id, session.household_id)


def logout(uow: UnitOfWork, token: str) -> None:
    if token:
        uow.sessions.delete(_hash_token(token))
        uow.commit()


def me(uow: UnitOfWork, actor: Actor) -> Me:
    user = uow.users.get(actor.user_id)
    household = uow.households.get(actor.household_id)
    if user is None or household is None:
        raise NotFoundError("Sesión sin usuario u hogar")
    return Me(user, household, uow.households.members(actor.household_id))
