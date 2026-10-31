from fastapi import APIRouter

from openfinance.api.v1 import meta

router = APIRouter(prefix="/api/v1")
router.include_router(meta.router)
