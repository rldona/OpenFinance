"""Comercios: listar, renombrar y fusionar (OF-1001)."""

from fastapi import APIRouter

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    MerchantChangeOut,
    MerchantGroupOut,
    MerchantMergeIn,
    MerchantRenameIn,
    MoneyOut,
)
from openfinance.application import merchants
from openfinance.application.ports import UnitOfWork
from openfinance.domain.shared import Money
from openfinance.domain.workspaces import Actor
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["merchants"])


def _out(uow: UnitOfWork, actor: Actor, view: merchants.MerchantView) -> MerchantGroupOut:
    currency = _currency(uow, actor)
    return MerchantGroupOut(
        id=view.id,
        name=view.name,
        keys=view.keys,
        count=view.count,
        total=MoneyOut.of(Money.of(view.total, currency)),
    )


def _currency(uow: UnitOfWork, actor: Actor) -> str:
    household = uow.households.get(actor.household_id)
    return household.currency.code if household else "EUR"


@router.get("/merchants", response_model=list[MerchantGroupOut])
def list_merchants(actor: ActorDep, uow: UowDep) -> list[MerchantGroupOut]:
    return [_out(uow, actor, v) for v in merchants.list_merchants(uow, actor)]


@router.post("/merchants/rename", response_model=MerchantChangeOut)
def rename_merchant(body: MerchantRenameIn, actor: ActorDep, uow: UowDep) -> MerchantChangeOut:
    view, operation_id = merchants.rename_merchant(uow, actor, body.key, body.name, utc_now())
    return MerchantChangeOut(
        merchant=_out(uow, actor, view), reclassified=0, operation_id=operation_id
    )


@router.post("/merchants/merge", response_model=MerchantChangeOut)
def merge_merchants(body: MerchantMergeIn, actor: ActorDep, uow: UowDep) -> MerchantChangeOut:
    result = merchants.merge_merchants(uow, actor, body.target_key, body.source_key, utc_now())
    return MerchantChangeOut(
        merchant=_out(uow, actor, result.merchant),
        reclassified=result.reclassified,
        operation_id=result.operation_id,
    )
