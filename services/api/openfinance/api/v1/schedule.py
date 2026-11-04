"""Pagos programados (ADR-0021, OF-1201)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    AllowanceOut,
    ForecastOut,
    ForecastViewOut,
    MoneyOut,
    OccurrenceOut,
    OperationRefOut,
    ScheduledPaymentChangeOut,
    ScheduledPaymentIn,
    ScheduledPaymentOut,
    ScheduleItemOut,
)
from openfinance.application import schedule
from openfinance.application.allowance import household_allowance
from openfinance.application.forecast import household_forecast
from openfinance.application.schedule import DEFAULT_HORIZON_DAYS, MAX_HORIZON_DAYS
from openfinance.infrastructure.time import local_today, utc_now

router = APIRouter(tags=["schedule"])


def _draft(body: ScheduledPaymentIn) -> schedule.PaymentDraft:
    return schedule.PaymentDraft(**body.model_dump())


@router.get("/schedule", response_model=list[ScheduleItemOut])
def list_schedule(
    actor: ActorDep,
    uow: UowDep,
    days: Annotated[int, Query(ge=1, le=MAX_HORIZON_DAYS)] = DEFAULT_HORIZON_DAYS,
) -> list[ScheduleItemOut]:
    today = local_today()
    return [
        ScheduleItemOut(
            payment=ScheduledPaymentOut.of(v.payment),
            occurrences=[
                OccurrenceOut(
                    due=o.due,
                    amount=MoneyOut.of(o.amount),
                    status=o.status,
                    transaction_id=o.transaction_id,
                )
                for o in v.occurrences
            ],
        )
        for v in schedule.list_schedule(uow, actor, today, days)
    ]


@router.post(
    "/schedule", response_model=ScheduledPaymentChangeOut, status_code=status.HTTP_201_CREATED
)
def create_payment(
    body: ScheduledPaymentIn, actor: ActorDep, uow: UowDep
) -> ScheduledPaymentChangeOut:
    payment, operation_id = schedule.create_payment(uow, actor, _draft(body), utc_now())
    return ScheduledPaymentChangeOut(
        payment=ScheduledPaymentOut.of(payment), operation_id=operation_id
    )


@router.put("/schedule/{schedule_id}", response_model=ScheduledPaymentChangeOut)
def update_payment(
    schedule_id: UUID, body: ScheduledPaymentIn, actor: ActorDep, uow: UowDep
) -> ScheduledPaymentChangeOut:
    payment, operation_id = schedule.update_payment(
        uow, actor, schedule_id, _draft(body), utc_now()
    )
    return ScheduledPaymentChangeOut(
        payment=ScheduledPaymentOut.of(payment), operation_id=operation_id
    )


@router.delete("/schedule/{schedule_id}", response_model=OperationRefOut)
def delete_payment(schedule_id: UUID, actor: ActorDep, uow: UowDep) -> OperationRefOut:
    return OperationRefOut(operation_id=schedule.delete_payment(uow, actor, schedule_id, utc_now()))


@router.get("/forecast", response_model=ForecastViewOut)
def forecast(
    actor: ActorDep,
    uow: UowDep,
    days: Annotated[int, Query(ge=1, le=MAX_HORIZON_DAYS)] = DEFAULT_HORIZON_DAYS,
) -> ForecastViewOut:
    """Saldo previsto de cada cuenta de efectivo y total por moneda (OF-1202)."""
    view = household_forecast(uow, actor, local_today(), days)
    return ForecastViewOut(
        until=view.until,
        accounts=[
            ForecastOut.of(a.forecast, a.account.currency.code, a.account) for a in view.accounts
        ],
        totals=[ForecastOut.of(t.forecast, t.currency.code) for t in view.totals],
    )


@router.get("/allowance", response_model=AllowanceOut)
def allowance(actor: ActorDep, uow: UowDep) -> AllowanceOut:
    """Cuánto se puede gastar al día con el dinero de la conjunta (OF-1205)."""
    return AllowanceOut.of(household_allowance(uow, actor, local_today()))
