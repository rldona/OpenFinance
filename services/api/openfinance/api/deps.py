from collections.abc import Iterator
from datetime import timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from openfinance.application.identity import resolve_session
from openfinance.domain.workspaces import Actor
from openfinance.infrastructure.attachments import FileAttachmentStore
from openfinance.infrastructure.config import Settings, get_settings
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from openfinance.infrastructure.db.session import get_session_factory
from openfinance.infrastructure.enablebanking import EnableBankingAggregator
from openfinance.infrastructure.importers import StatementParserRegistry
from openfinance.infrastructure.security import Argon2PasswordHasher
from openfinance.infrastructure.throttle import LoginThrottle
from openfinance.infrastructure.time import utc_now
from openfinance.infrastructure.updates import GithubLatestRelease


def get_uow(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> Iterator[SqlUnitOfWork]:
    with factory() as session:
        yield SqlUnitOfWork(session)


@lru_cache
def get_hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()


@lru_cache
def get_login_throttle() -> LoginThrottle:
    settings = get_settings()
    return LoginThrottle(
        settings.login_max_failures_per_email,
        settings.login_max_failures_per_ip,
        timedelta(minutes=settings.login_window_minutes),
    )


SettingsDep = Annotated[Settings, Depends(get_settings)]
ThrottleDep = Annotated[LoginThrottle, Depends(get_login_throttle)]
UowDep = Annotated[SqlUnitOfWork, Depends(get_uow)]
HasherDep = Annotated[Argon2PasswordHasher, Depends(get_hasher)]


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_VIEWER_MAY_WRITE = frozenset(
    {
        ("POST", "/api/v1/me/password"),
        ("POST", "/api/v1/me/sessions/revoke-others"),
        ("POST", "/api/v1/alerts/dismiss"),
        ("POST", "/api/v1/notifications/subscriptions"),
        ("POST", "/api/v1/notifications/subscriptions/remove"),
        ("PUT", "/api/v1/notifications/preferences"),
        ("POST", "/api/v1/reports/run"),
    }
)
"""Lo que un ``viewer`` puede pedir sin ser lectura: lo suyo (contraseña, sesiones, avisos y
notificaciones) y ejecutar informes. Todo lo demás que escribe datos del hogar, no (ADR-0026)."""


def get_actor(request: Request, uow: UowDep, settings: SettingsDep) -> Actor:
    token = request.cookies.get(settings.session_cookie_name, "")
    actor = resolve_session(uow, token, utc_now())
    if actor is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión")
    if (
        not actor.role.can_write
        and request.method not in _SAFE_METHODS
        and (request.method, request.url.path) not in _VIEWER_MAY_WRITE
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu rol en el hogar solo permite leer")
    return actor


ActorDep = Annotated[Actor, Depends(get_actor)]


@lru_cache
def get_release_source() -> GithubLatestRelease | None:
    """La consulta de versión nueva, o ``None`` si está apagada (por defecto, OF-907)."""
    settings = get_settings()
    return GithubLatestRelease(settings.update_repo) if settings.update_check else None


@lru_cache
def get_attachment_store() -> FileAttachmentStore:
    return FileAttachmentStore(get_settings().attachments_dir)


@lru_cache
def get_parsers() -> StatementParserRegistry:
    return StatementParserRegistry()


AttachmentStoreDep = Annotated[FileAttachmentStore, Depends(get_attachment_store)]
ReleaseSourceDep = Annotated[GithubLatestRelease | None, Depends(get_release_source)]
ParsersDep = Annotated[StatementParserRegistry, Depends(get_parsers)]


@lru_cache
def get_bank_aggregator() -> EnableBankingAggregator:
    return EnableBankingAggregator(get_settings())


BankAggregatorDep = Annotated[EnableBankingAggregator, Depends(get_bank_aggregator)]
