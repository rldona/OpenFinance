from fastapi import APIRouter

from openfinance.api.v1 import auth, ledger, meta

router = APIRouter(prefix="/api/v1")
router.include_router(meta.router)
router.include_router(auth.router)
router.include_router(ledger.router)
