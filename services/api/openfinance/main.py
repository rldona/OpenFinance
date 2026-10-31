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
from openfinance.domain.imports.batch import MAX_FILE_BYTES
from openfinance.infrastructure.config import Settings, get_settings

CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "OpenFinance"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_STATUS = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidRequestError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


async def _application_error(_: Request, exc: Exception) -> JSONResponse:
    code = next((c for t, c in _STATUS.items() if isinstance(exc, t)), 400)
    return JSONResponse({"detail": str(exc)}, status_code=code)


_MAX_BODY_BYTES = MAX_FILE_BYTES + 64 * 1024


async def _limit_body_size(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Rechaza cuerpos grandes antes de recibirlos (el proxy también lo limita)."""
    length = request.headers.get("content-length")
    if length is not None and (not length.isdigit() or int(length) > _MAX_BODY_BYTES):
        return JSONResponse(
            {"detail": "El archivo es demasiado grande (máximo 5 MB)"},
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )
    return await call_next(request)


async def _require_csrf_header(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Las escrituras exigen una cabecera propia.

    Un formulario de otra web no puede enviarla, y desde JavaScript obliga a una petición
    previa de CORS que solo aceptan los orígenes configurados.
    """
    if (
        request.method not in _SAFE_METHODS
        and request.url.path.startswith("/api/")
        and request.headers.get(CSRF_HEADER) != CSRF_VALUE
    ):
        return JSONResponse(
            {"detail": f"Falta la cabecera {CSRF_HEADER}: {CSRF_VALUE}"},
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return await call_next(request)


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
    # El último en añadirse es el más externo: CORS envuelve al resto para que también
    # las respuestas 403/413 lleven sus cabeceras.
    app.middleware("http")(_require_csrf_header)
    app.middleware("http")(_limit_body_size)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER],
    )
    app.add_exception_handler(ApplicationError, _application_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()
