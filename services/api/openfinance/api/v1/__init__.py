from fastapi import APIRouter

from openfinance.api.v1 import (
    auth,
    categories,
    export,
    imports,
    insights,
    ledger,
    meta,
    savings,
)

router = APIRouter(prefix="/api/v1")
router.include_router(meta.router)
router.include_router(auth.router)
router.include_router(categories.router)
router.include_router(ledger.router)
router.include_router(imports.router)
router.include_router(insights.router)
router.include_router(savings.router)
router.include_router(export.router)
