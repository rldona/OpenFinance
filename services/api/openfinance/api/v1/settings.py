"""Ajustes de cada persona: contraseña, sesiones y tarjetas de recarga (OF-704)."""

from fastapi import APIRouter, HTTPException, Request, status

from openfinance.api.deps import ActorDep, HasherDep, SettingsDep, ThrottleDep, UowDep
from openfinance.api.v1.schemas import PasswordChangeIn, PatternIn, PatternOut, RevokedOut
from openfinance.application import identity
from openfinance.application import member_patterns as mp
from openfinance.application.errors import WrongPasswordError
from openfinance.domain.imports import PatternDirection
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["settings"])


@router.post("/me/password", response_model=RevokedOut)
def change_password(
    body: PasswordChangeIn,
    request: Request,
    actor: ActorDep,
    uow: UowDep,
    hasher: HasherDep,
    settings: SettingsDep,
    throttle: ThrottleDep,
) -> RevokedOut:
    """Cambia tu contraseña (pide la actual) y cierra tus sesiones en otros navegadores."""
    now = utc_now()
    ip = request.client.host if request.client else "unknown"
    key = f"password:{actor.user_id}"
    if throttle.is_blocked(key, ip, now):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos. Espera unos minutos."
        )
    try:
        revoked = identity.change_own_password(
            uow,
            hasher,
            actor,
            body.current_password,
            body.new_password,
            request.cookies.get(settings.session_cookie_name, ""),
        )
    except WrongPasswordError:
        throttle.record_failure(key, ip, now)
        raise
    throttle.reset(key)
    return RevokedOut(revoked=revoked)


@router.post("/me/sessions/revoke-others", response_model=RevokedOut)
def revoke_other_sessions(
    request: Request, actor: ActorDep, uow: UowDep, settings: SettingsDep
) -> RevokedOut:
    """Cierra tus sesiones en otros navegadores y dispositivos; esta sigue abierta."""
    token = request.cookies.get(settings.session_cookie_name, "")
    return RevokedOut(revoked=identity.revoke_other_sessions(uow, actor, token))


@router.get("/me/patterns", response_model=list[PatternOut])
def own_patterns(actor: ActorDep, uow: UowDep) -> list[PatternOut]:
    """Tus patrones: p. ej. «*1234», el final de la tarjeta con la que recargas la conjunta."""
    return [
        PatternOut(pattern=p.pattern, direction=p.direction) for p in mp.own_patterns(uow, actor)
    ]


@router.post("/me/patterns", response_model=PatternOut, status_code=status.HTTP_201_CREATED)
def add_pattern(body: PatternIn, actor: ActorDep, uow: UowDep) -> PatternOut:
    p = mp.add_own_pattern(uow, actor, body.pattern, body.direction, utc_now())
    return PatternOut(pattern=p.pattern, direction=p.direction)


@router.delete("/me/patterns/{direction}/{pattern}", status_code=status.HTTP_204_NO_CONTENT)
def remove_pattern(direction: PatternDirection, pattern: str, actor: ActorDep, uow: UowDep) -> None:
    mp.remove_own_pattern(uow, actor, pattern, direction)
