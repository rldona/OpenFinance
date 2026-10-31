from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from openfinance import __version__
from openfinance.api import health, v1
from openfinance.application.errors import (
    ApplicationError,
    AuthenticationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from openfinance.infrastructure.config import Settings, get_settings

_STATUS = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidRequestError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


async def _application_error(_: Request, exc: Exception) -> JSONResponse:
    code = next((c for t, c in _STATUS.items() if isinstance(exc, t)), 400)
    return JSONResponse({"detail": str(exc)}, status_code=code)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    """Como el de FastAPI, pero sin devolver los valores enviados (p. ej. contraseñas)."""
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    detail = [{k: v for k, v in e.items() if k in ("type", "loc", "msg")} for e in errors]
    return JSONResponse({"detail": detail}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="OpenFinance API",
        version=__version__,
        license_info={"name": "AGPL-3.0-or-later", "identifier": "AGPL-3.0-or-later"},
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.add_exception_handler(ApplicationError, _application_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()
