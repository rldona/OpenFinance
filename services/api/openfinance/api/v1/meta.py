from fastapi import APIRouter
from pydantic import BaseModel

from openfinance import __version__
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
