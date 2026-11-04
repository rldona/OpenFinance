from fastapi import APIRouter
from pydantic import BaseModel, Field

from openfinance import __version__
from openfinance.api.deps import ActorDep, ReleaseSourceDep
from openfinance.application import updates
from openfinance.domain import BOUNDED_CONTEXTS

router = APIRouter(tags=["meta"])


class MetaResponse(BaseModel):
    name: str
    version: str
    api_version: str
    contexts: list[str]


@router.get("/meta", response_model=MetaResponse)
def get_meta() -> MetaResponse:
    return MetaResponse(
        name="OpenFinance",
        version=__version__,
        api_version="v1",
        contexts=list(BOUNDED_CONTEXTS),
    )


class VersionOut(BaseModel):
    current: str
    enabled: bool = Field(description="Si la consulta de versión nueva está activada")
    latest: str | None = Field(description="Última release publicada, si se ha podido saber")
    url: str | None = Field(description="Página de esa release en GitHub")
    update_available: bool


@router.get("/version", response_model=VersionOut)
def get_version(_: ActorDep, source: ReleaseSourceDep) -> VersionOut:
    """Versión instalada y, si `OPENFINANCE_UPDATE_CHECK` está activada, si hay una nueva.
    Solo avisa: la actualización la hace quien administra la instalación."""
    info = updates.version_info(__version__, source)
    return VersionOut(
        current=info.current,
        enabled=info.enabled,
        latest=info.latest,
        url=info.url,
        update_available=info.update_available,
    )
