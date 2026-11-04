from fastapi import APIRouter

from openfinance.api.v1 import (
    alerts,
    attachments,
    auth,
    automation,
    categories,
    changes,
    csv_profiles,
    export,
    imports,
    insights,
    ledger,
    merchants,
    meta,
    notifications,
    rates,
    savings,
    schedule,
    settings,
    summary,
    templates,
)

router = APIRouter(prefix="/api/v1")
router.include_router(meta.router)
router.include_router(merchants.router)
router.include_router(rates.router)
router.include_router(attachments.router)
router.include_router(automation.router)
router.include_router(auth.router)
router.include_router(categories.router)
router.include_router(csv_profiles.router)
router.include_router(ledger.router)
router.include_router(imports.router)
router.include_router(insights.router)
router.include_router(savings.router)
router.include_router(schedule.router)
router.include_router(templates.router)
router.include_router(alerts.router)
router.include_router(notifications.router)
router.include_router(summary.router)
router.include_router(export.router)
router.include_router(changes.router)
router.include_router(settings.router)
