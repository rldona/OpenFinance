from fastapi import APIRouter

from openfinance.api.v1 import (
    attachments,
    auth,
    categories,
    changes,
    export,
    imports,
    insights,
    ledger,
    merchants,
    meta,
    savings,
    settings,
)

router = APIRouter(prefix="/api/v1")
router.include_router(meta.router)
router.include_router(merchants.router)
router.include_router(attachments.router)
router.include_router(auth.router)
router.include_router(categories.router)
router.include_router(ledger.router)
router.include_router(imports.router)
router.include_router(insights.router)
router.include_router(savings.router)
router.include_router(export.router)
router.include_router(changes.router)
router.include_router(settings.router)
