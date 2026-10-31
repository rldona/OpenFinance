from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openfinance import __version__
from openfinance.api import health, v1
from openfinance.infrastructure.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="OpenFinance API",
        version=__version__,
        license_info={"name": "AGPL-3.0-or-later", "identifier": "AGPL-3.0-or-later"},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()
