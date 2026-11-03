import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from openfinance.api.deps import ActorDep, HasherDep, SettingsDep, ThrottleDep, UowDep
from openfinance.api.v1.schemas import (
    HouseholdOut,
    InvitationAcceptIn,
    LoginIn,
    MemberOut,
    MeOut,
    UserOut,
)
from openfinance.application import identity, members
from openfinance.application.errors import AuthenticationError
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _warn_secure_cookie_over_http(request: Request, secure: bool) -> None:
    """El navegador descarta una cookie Secure recibida por http (salvo en localhost)."""
    if secure and request.url.scheme == "http" and request.url.hostname not in _LOCAL_HOSTS:
        logger.warning(
            "Cookie de sesión Secure sobre http: el navegador no guardará la sesión. "
            "Sirve por HTTPS o pon OPENFINANCE_SESSION_COOKIE_SECURE=false dentro de casa."
        )


@router.post("/auth/login", response_model=MeOut)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    uow: UowDep,
    hasher: HasherDep,
    settings: SettingsDep,
    throttle: ThrottleDep,
) -> MeOut:
    """Primero se cuenta el intento (atómico), luego se busca a la persona, se verifica la
    contraseña en los hilos de Argon2 y se abre la sesión. Los accesos a la base de datos van
    al grupo de hilos común; Argon2, no (OF-906)."""
    now = utc_now()
    ip = request.client.host if request.client else "unknown"
    if not throttle.try_acquire(body.email, ip, now):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiados intentos. Espera unos minutos.",
            headers={"Retry-After": str(settings.login_window_minutes * 60)},
        )
    user = await run_in_threadpool(identity.find_login_user, uow, body.email)
    if not await hasher.averify(user.password_hash if user else None, body.password):
        raise AuthenticationError
    assert user is not None  # averify(None, ...) siempre devuelve False
    session = await run_in_threadpool(
        identity.open_session,
        uow,
        user,
        now,
        timedelta(days=settings.session_ttl_days),
        request.cookies.get(settings.session_cookie_name, ""),
    )
    throttle.release_success(body.email, ip, now)
    _warn_secure_cookie_over_http(request, settings.cookie_secure)
    response.set_cookie(
        settings.session_cookie_name,
        session.token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return _me(await run_in_threadpool(identity.me, uow, session.actor))


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, uow: UowDep, settings: SettingsDep) -> None:
    identity.logout(uow, request.cookies.get(settings.session_cookie_name, ""))
    response.delete_cookie(
        settings.session_cookie_name, path="/", secure=settings.cookie_secure, httponly=True
    )


@router.get("/me", response_model=MeOut)
def get_me(actor: ActorDep, uow: UowDep) -> MeOut:
    return _me(identity.me(uow, actor))


def _me(me: identity.Me) -> MeOut:
    return MeOut(
        user=UserOut.of(me.user),
        household=HouseholdOut.of(me.household),
        members=[MemberOut(id=m.id, display_name=m.display_name) for m in me.members],
        role=me.role.value,
    )


@router.post("/auth/invitations/accept", response_model=MeOut, status_code=status.HTTP_201_CREATED)
async def accept_invitation(
    body: InvitationAcceptIn,
    request: Request,
    response: Response,
    uow: UowDep,
    hasher: HasherDep,
    settings: SettingsDep,
    throttle: ThrottleDep,
) -> MeOut:
    """Une a una persona nueva al hogar con una invitación vigente (ADR-0026).

    No hay registro público: sin un enlace válido no se crea nada. Cada intento cuenta contra
    el límite por IP, como el inicio de sesión, y todo fallo da el mismo mensaje.
    """
    now = utc_now()
    ip = request.client.host if request.client else "unknown"
    # La clave «email» es la propia IP: un tercero no puede bloquear las invitaciones de todos.
    key = f"invitation:{ip}"
    if not throttle.try_acquire(key, ip, now):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiados intentos. Espera unos minutos.",
            headers={"Retry-After": str(settings.login_window_minutes * 60)},
        )
    session = await run_in_threadpool(
        members.accept_invitation,
        uow,
        hasher,
        body.token,
        body.display_name,
        body.email,
        body.password,
        now,
        timedelta(days=settings.session_ttl_days),
    )
    throttle.release_success(key, ip, now)
    response.set_cookie(
        settings.session_cookie_name,
        session.token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return _me(await run_in_threadpool(identity.me, uow, session.actor))
