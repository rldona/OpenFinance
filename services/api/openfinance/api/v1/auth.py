from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status

from openfinance.api.deps import ActorDep, HasherDep, SettingsDep, ThrottleDep, UowDep
from openfinance.api.v1.schemas import HouseholdOut, LoginIn, MemberOut, MeOut, UserOut
from openfinance.application import identity
from openfinance.application.errors import AuthenticationError
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=MeOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    uow: UowDep,
    hasher: HasherDep,
    settings: SettingsDep,
    throttle: ThrottleDep,
) -> MeOut:
    now = utc_now()
    ip = request.client.host if request.client else "unknown"
    if throttle.is_blocked(body.email, ip, now):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiados intentos. Espera unos minutos.",
            headers={"Retry-After": str(settings.login_window_minutes * 60)},
        )
    try:
        session = identity.login(
            uow,
            hasher,
            body.email,
            body.password,
            now,
            timedelta(days=settings.session_ttl_days),
            previous_token=request.cookies.get(settings.session_cookie_name, ""),
        )
    except AuthenticationError:
        throttle.record_failure(body.email, ip, now)
        raise
    throttle.reset(body.email)
    response.set_cookie(
        settings.session_cookie_name,
        session.token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return _me(identity.me(uow, session.actor))


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
    )
