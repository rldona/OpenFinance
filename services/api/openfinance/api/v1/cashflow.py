"""Flujo de caja mensual (ADR-0025, OF-1502)."""

from typing import Annotated

from fastapi import APIRouter, Query

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import CashFlowOut, MoneyOut, MonthFlowOut
from openfinance.application import cashflow
from openfinance.domain.cashflow import DEFAULT_MONTHS, MAX_MONTHS
from openfinance.infrastructure.time import local_today

router = APIRouter(tags=["cash-flow"])


@router.get("/cash-flow", response_model=CashFlowOut)
def get_cash_flow(
    actor: ActorDep,
    uow: UowDep,
    months: Annotated[int, Query(ge=1, le=MAX_MONTHS)] = DEFAULT_MONTHS,
) -> CashFlowOut:
    result = cashflow.cash_flow(uow, actor, local_today(), months)
    return CashFlowOut(
        currency=result.currency.code,
        months=[
            MonthFlowOut(
                month=str(m.month),
                income=MoneyOut.of(m.income),
                contributions=MoneyOut.of(m.contributions),
                spending=MoneyOut.of(m.spending),
                savings=MoneyOut.of(m.savings),
                transfers=MoneyOut.of(m.transfers),
                change=MoneyOut.of(m.change),
                end_balance=MoneyOut.of(m.end_balance),
                is_partial=m.is_partial,
            )
            for m in result.months
        ],
        accounts=result.accounts,
        excluded_foreign=result.excluded_foreign,
    )
