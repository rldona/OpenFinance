"""Tipos de cambio manuales y monedas sin tipo (ADR-0019, OF-1008)."""

from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from openfinance.api.deps import ActorDep, SettingsDep, UowDep
from openfinance.api.v1.schemas import MissingRateOut, OperationRefOut, RateIn, RateOut, RateSetOut
from openfinance.application import conversion
from openfinance.domain.rates import ExchangeRate
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["rates"])


def _out(r: ExchangeRate) -> RateOut:
    return RateOut(currency=r.currency.code, on=r.on, rate=f"{r.rate:f}", source=r.source)


@router.get("/exchange-rates", response_model=list[RateOut])
def list_rates(actor: ActorDep, uow: UowDep) -> list[RateOut]:
    """Los tipos de cambio del hogar: 1 unidad de la moneda = tanto de la moneda del hogar."""
    return [_out(r) for r in conversion.list_rates(uow, actor)]


@router.put("/exchange-rates", response_model=RateSetOut)
def set_rate(body: RateIn, actor: ActorDep, uow: UowDep, settings: SettingsDep) -> RateSetOut:
    """Pone o corrige el tipo de cambio de una moneda en una fecha; se puede deshacer."""
    today = utc_now().astimezone(ZoneInfo(settings.timezone)).date()
    rate, operation_id = conversion.set_rate(
        uow, actor, body.currency, body.on, body.rate, utc_now(), today
    )
    return RateSetOut(rate=_out(rate), operation_id=operation_id)


@router.delete("/exchange-rates/{currency}/{on}", response_model=OperationRefOut)
def delete_rate(currency: str, on: date, actor: ActorDep, uow: UowDep) -> OperationRefOut:
    return OperationRefOut(operation_id=conversion.delete_rate(uow, actor, currency, on, utc_now()))


@router.get("/exchange-rates/missing", response_model=list[MissingRateOut])
def missing_rates(actor: ActorDep, uow: UowDep) -> list[MissingRateOut]:
    """Monedas con movimientos tuyos que no entran en los informes por falta de tipo."""
    return [
        MissingRateOut(currency=m.currency, count=m.count, first=m.first)
        for m in conversion.missing_rates(uow, actor)
    ]
