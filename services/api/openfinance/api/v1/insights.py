from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    CategoryAmountOut,
    CategoryDetailOut,
    MemberAmountOut,
    MerchantOut,
    MoneyOut,
    MonthAmountOut,
    MonthOverviewOut,
    MonthSavedOut,
    TrendCategoryOut,
    TrendMonthOut,
    TrendsOut,
)
from openfinance.application import insights
from openfinance.domain.categories import CategoryId, merchant_label
from openfinance.domain.insights import Month
from openfinance.domain.shared import Money
from openfinance.infrastructure.time import local_today

router = APIRouter(prefix="/insights", tags=["insights"])

MonthParam = Annotated[
    str | None,
    Query(
        pattern=r"^(19|2\d)\d{2}-(0[1-9]|1[0-2])$", description="AAAA-MM; por defecto, el actual"
    ),
]


ViewParam = Annotated[
    insights.View,
    Query(description="household = conjunta y huchas; mine = tus cuentas personales"),
]


def _month(value: str | None) -> Month:
    return Month.parse(value) if value else Month.of(local_today())


def _money(m: Money | None) -> MoneyOut | None:
    return MoneyOut.of(m) if m is not None else None


def _category_amount(c: insights.CategoryAmount) -> CategoryAmountOut:
    return CategoryAmountOut(
        category_id=c.category_id,
        amount=MoneyOut.of(c.amount),
        average=_money(c.average),
        reference=_money(c.reference),
        change=_money(c.change),
    )


@router.get("/month", response_model=MonthOverviewOut)
def month_overview(
    actor: ActorDep,
    uow: UowDep,
    month: MonthParam = None,
    view: ViewParam = insights.View.HOUSEHOLD,
) -> MonthOverviewOut:
    """Resumen de un mes: lo que se gasta, entra y ahorra (o, en «mío», lo que aportas)."""
    o = insights.month_overview(uow, actor, _month(month), local_today(), view)
    return MonthOverviewOut(
        month=str(o.month),
        has_data=o.has_data,
        spent=MoneyOut.of(o.summary.spent),
        previous_spent=_money(o.previous_spent),
        is_partial=o.is_partial,
        days_elapsed=o.days_elapsed,
        previous_spent_to_date=_money(o.previous_spent_to_date),
        average_spent=_money(o.average_spent),
        inflow=MoneyOut.of(o.summary.inflow),
        income=MoneyOut.of(o.summary.income),
        saved=MoneyOut.of(o.summary.saved),
        saved_to_savings=MoneyOut.of(o.summary.saved_to_savings),
        saving_rate=o.saving_rate,
        contributions=[
            MemberAmountOut(member_id=k, amount=MoneyOut.of(v)) for k, v in o.contributions.items()
        ],
        contributed=MoneyOut.of(o.contributed),
        categories=[_category_amount(c) for c in o.categories],
        changes=[_category_amount(c) for c in o.changes],
        currency=o.currency.code,
        daily=[str(m.amount) for m in o.daily],
        previous_daily=[str(m.amount) for m in o.previous_daily],
    )


@router.get("/category", response_model=CategoryDetailOut)
def category_detail(
    actor: ActorDep,
    uow: UowDep,
    month: MonthParam = None,
    category_id: Annotated[UUID | None, Query(description="Vacío = sin categoría")] = None,
    view: ViewParam = insights.View.HOUSEHOLD,
) -> CategoryDetailOut:
    """Una categoría en los últimos 12 meses y sus comercios principales."""
    d = insights.category_detail(
        uow, actor, CategoryId(category_id) if category_id else None, _month(month), view
    )
    return CategoryDetailOut(
        category_id=d.category_id,
        month=str(d.month),
        months=[
            MonthAmountOut(month=str(m.month), amount=MoneyOut.of(m.amount), has_data=m.has_data)
            for m in d.months
        ],
        average=_money(d.average),
        merchants=[
            MerchantOut(
                merchant=merchant_label(m.merchant), amount=MoneyOut.of(m.spent), count=m.count
            )
            for m in d.merchants
        ],
    )


@router.get("/trends", response_model=TrendsOut)
def trends(
    actor: ActorDep,
    uow: UowDep,
    month: MonthParam = None,
    months: Annotated[int, Query(ge=2, le=36)] = 12,
) -> TrendsOut:
    """Evolución mensual hasta ``month``: gasto, entradas, ahorro y gasto por categoría."""
    t = insights.trends(uow, actor, _month(month), local_today(), months)

    def saved(item: insights.TrendMonth | None) -> MonthSavedOut | None:
        return (
            MonthSavedOut(month=str(item.month), saved=MoneyOut.of(item.summary.saved))
            if item
            else None
        )

    return TrendsOut(
        months=[
            TrendMonthOut(
                month=str(m.month),
                has_data=m.has_data,
                is_partial=m.is_partial,
                spent=MoneyOut.of(m.summary.spent),
                inflow=MoneyOut.of(m.summary.inflow),
                saved=MoneyOut.of(m.summary.saved),
                categories=[
                    TrendCategoryOut(category_id=k, amount=MoneyOut.of(v))
                    for k, v in m.categories.items()
                ],
            )
            for m in t.months
        ],
        total_saved=MoneyOut.of(t.total_saved),
        total_inflow=MoneyOut.of(t.total_inflow),
        total_spent=MoneyOut.of(t.total_spent),
        average_spent=_money(t.average_spent),
        average_saved=_money(t.average_saved),
        saving_rate=t.saving_rate,
        best=saved(t.best),
        worst=saved(t.worst),
    )
