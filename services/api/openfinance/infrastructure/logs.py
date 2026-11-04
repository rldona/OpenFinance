"""Logging de la API (OF-904): un formato, el nivel de `OPENFINANCE_LOG_LEVEL` y el
identificador de la petición en cada línea.

Nunca se registran cuerpos, cookies, cabeceras ni la query de la URL (la búsqueda de
movimientos puede llevar texto personal): solo método, ruta, estado y duración.
"""

import logging
import re
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"


def sanitize_request_id(value: str | None) -> str | None:
    """Un identificador que llega de fuera solo vale si es corto y sin caracteres raros
    (evita inyectar saltos de línea en los logs)."""
    return value if value and _VALID_REQUEST_ID.match(value) else None


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def parse_level(name: str) -> int:
    level = logging.getLevelName(name.upper())
    if not isinstance(level, int):
        raise ValueError(f"Nivel de log no válido: {name}")
    return level


def configure_logging(level_name: str) -> None:
    """Idempotente: se puede llamar al crear cada aplicación (tests incluidos)."""
    level = parse_level(level_name)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        if getattr(handler, "_openfinance", False):
            handler.setLevel(level)
            return
    handler = logging.StreamHandler()
    handler._openfinance = True  # type: ignore[attr-defined]
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.addFilter(_RequestIdFilter())
    root.addHandler(handler)
    # Uvicorn escribe sus propios errores con su formato; el acceso lo registra la API sin la
    # query de la URL.
    logging.getLogger("uvicorn.access").disabled = True
