"""Resumen semanal (ADR-0023, OF-1303)."""

from fastapi import APIRouter

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    MoneyOut,
    UpcomingPaymentOut,
    WeekCategoryOut,
    WeeklySummaryOut,
)
from openfinance.application.weekly import weekly_summary
from openfinance.infrastructure.time import local_today

router = APIRouter(tags=["summary"])


@router.get("/summary/weekly", response_model=WeeklySummaryOut)
def weekly(actor: ActorDep, uow: UowDep) -> WeeklySummaryOut:
    """La última semana completa frente a la anterior, para las cuentas que ves."""
    s = weekly_summary(uow, actor, local_today())
    return WeeklySummaryOut(
        start=s.start,
        end=s.end,
        spent=MoneyOut.of(s.spent),
        previous=MoneyOut.of(s.previous),
        change_percent=s.change_percent,
        top=[
            WeekCategoryOut(category_id=c.category_id, amount=MoneyOut.of(c.amount)) for c in s.top
        ],
        upcoming=[
            UpcomingPaymentOut(
                name=u.name, due=u.occurrence.due, amount=MoneyOut.of(u.occurrence.amount)
            )
            for u in s.upcoming
        ],
        open_alerts=s.open_alerts,
    )
