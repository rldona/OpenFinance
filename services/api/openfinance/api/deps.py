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


def get_actor(request: Request, uow: UowDep, settings: SettingsDep) -> Actor:
    token = request.cookies.get(settings.session_cookie_name, "")
    actor = resolve_session(uow, token, utc_now())
    if actor is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión")
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
