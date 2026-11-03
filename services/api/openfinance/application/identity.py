"""Inicio de sesión y sesiones (OF-101)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from openfinance.application.errors import (
    AuthenticationError,
    InvalidRequestError,
    NotFoundError,
    WrongPasswordError,
)
from openfinance.application.ports import PasswordHasher, StoredSession, UnitOfWork
from openfinance.domain.identity import (
    InvalidUserError,
    User,
    normalize_email,
    validate_password,
)
from openfinance.domain.workspaces import Actor, Household, Role


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
    role: Role = Role.OWNER


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def find_login_user(uow: UnitOfWork, email: str) -> User | None:
    """La persona de ese email, o ``None``. Primer paso del login (OF-906): la API verifica la
    contraseña después, fuera del grupo de hilos común."""
    try:
        return uow.users.get_by_email(normalize_email(email))
    except InvalidUserError:
        return None


def open_session(
    uow: UnitOfWork, user: User, now: datetime, ttl: timedelta, previous_token: str = ""
) -> NewSession:
    """Último paso del login, con la contraseña ya comprobada: abre la sesión, sustituye la
    que traiga el navegador y purga las caducadas."""
    households = uow.households.households_of(user.id)
    if not households:
        raise AuthenticationError
    if previous_token:
        uow.sessions.delete(_hash_token(previous_token))
    uow.sessions.delete_expired(now)
    # El extracto de una vista previa no confirmada no se guarda más de lo necesario (OF-607).
    uow.imports.purge_expired_content(now)
    token = secrets.token_urlsafe(32)
    session = StoredSession(_hash_token(token), user.id, households[0], now + ttl)
    uow.sessions.add(session)
    uow.commit()
    role = uow.households.role_of(session.household_id, user.id) or Role.VIEWER
    return NewSession(token, session.expires_at, Actor(user.id, session.household_id, role))


def login(
    uow: UnitOfWork,
    hasher: PasswordHasher,
    email: str,
    password: str,
    now: datetime,
    ttl: timedelta,
    previous_token: str = "",
) -> NewSession:
    """Inicia sesión de una vez (la API usa los pasos por separado para no bloquear)."""
    user = find_login_user(uow, email)
    if user is None:
        hasher.dummy_verify(password)
        raise AuthenticationError
    if not hasher.verify(user.password_hash, password):
        raise AuthenticationError
    return open_session(uow, user, now, ttl, previous_token)


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
    role = uow.households.role_of(session.household_id, session.user_id)
    if role is None:
        return None
    return Actor(session.user_id, session.household_id, role)


def logout(uow: UnitOfWork, token: str) -> None:
    if token:
        uow.sessions.delete(_hash_token(token))
        uow.commit()


def set_password(uow: UnitOfWork, hasher: PasswordHasher, email: str, password: str) -> int:
    """Cambia la contraseña de una persona y cierra sus sesiones. Devuelve cuántas había.

    Se usa desde el servidor (``openfinance users set-password``) cuando alguien la olvida.
    """
    try:
        normalized = normalize_email(email)
        validate_password(password)
    except InvalidUserError as exc:
        raise InvalidRequestError(str(exc)) from exc
    user = uow.users.get_by_email(normalized)
    if user is None:
        raise NotFoundError(f"No hay ninguna persona con el email {normalized}")
    uow.users.set_password_hash(user.id, hasher.hash(password))
    revoked = uow.sessions.delete_for_user(user.id)
    uow.commit()
    return revoked


def change_own_password(
    uow: UnitOfWork,
    hasher: PasswordHasher,
    actor: Actor,
    current: str,
    new: str,
    current_token: str,
) -> int:
    """Cambia la contraseña de quien está dentro (pide la actual) y cierra sus otras sesiones.

    Devuelve cuántas sesiones se han cerrado. La de este navegador sigue abierta.
    """
    user = uow.users.get(actor.user_id)
    if user is None or not hasher.verify(user.password_hash, current):
        raise WrongPasswordError("La contraseña actual no es correcta")
    try:
        validate_password(new)
    except InvalidUserError as exc:
        raise InvalidRequestError(str(exc)) from exc
    if new == current:
        raise InvalidRequestError("La nueva contraseña es igual que la actual")
    uow.users.set_password_hash(user.id, hasher.hash(new))
    revoked = uow.sessions.delete_for_user(user.id, keep=_hash_token(current_token))
    uow.commit()
    return revoked


def revoke_other_sessions(uow: UnitOfWork, actor: Actor, current_token: str) -> int:
    """Cierra las sesiones de quien pregunta en otros navegadores y dispositivos."""
    revoked = uow.sessions.delete_for_user(actor.user_id, keep=_hash_token(current_token))
    uow.commit()
    return revoked


def revoke_all_sessions(uow: UnitOfWork, now: datetime) -> int:
    """Cierra todas las sesiones y purga el contenido caducado de importaciones.

    Se usa tras restaurar una copia: las cookies emitidas antes dejan de valer.
    """
    revoked = uow.sessions.delete_all()
    uow.imports.purge_expired_content(now)
    uow.commit()
    return revoked


def me(uow: UnitOfWork, actor: Actor) -> Me:
    user = uow.users.get(actor.user_id)
    household = uow.households.get(actor.household_id)
    if user is None or household is None:
        raise NotFoundError("Sesión sin usuario u hogar")
    return Me(user, household, uow.households.members(actor.household_id), actor.role)
