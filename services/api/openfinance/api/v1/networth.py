"""Patrimonio neto (ADR-0025, OF-1501)."""

from fastapi import APIRouter

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    AccountWorthOut,
    MoneyOut,
    NetWorthOut,
    TypeWorthOut,
    WorthPointOut,
)
from openfinance.application import networth
from openfinance.domain.networth import WorthPoint
from openfinance.infrastructure.time import local_today

router = APIRouter(tags=["net-worth"])


def _point(p: WorthPoint) -> WorthPointOut:
    return WorthPointOut(
        on=p.on,
        assets=MoneyOut.of(p.assets),
        debts=MoneyOut.of(p.debts),
        net=MoneyOut.of(p.net),
        excluded=p.excluded,
    )


@router.get("/net-worth", response_model=NetWorthOut)
def get_net_worth(actor: ActorDep, uow: UowDep) -> NetWorthOut:
    result = networth.net_worth(uow, actor, local_today())
    return NetWorthOut(
        currency=result.currency_code,
        today=_point(result.today),
        history=[_point(p) for p in result.history],
        accounts=[
            AccountWorthOut(
                account_id=w.account.id,
                name=w.account.name,
                type=w.account.type.value,
                balance=MoneyOut.of(w.balance),
                value=MoneyOut.of(w.value) if w.value else None,
            )
            for w in result.accounts
        ],
        by_type=[TypeWorthOut(type=t.value, net=MoneyOut.of(m)) for t, m in result.by_type.items()],
        missing_rates=result.missing_rates,
    )
