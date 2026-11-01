import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from openfinance import __version__
from openfinance.infrastructure.db.session import get_session_factory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Está vivo: responde sin tocar la base de datos."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/ready", response_model=HealthResponse)
def ready(
    response: Response,
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> HealthResponse:
    """Está listo: la base de datos contesta. El detalle de un fallo va al log."""
    try:
        with factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        logger.warning("La base de datos no responde", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="unavailable", version=__version__)
    return HealthResponse(status="ok", version=__version__)
