"""Conexión con el banco por un agregador PSD2 (ADR-0024, OF-1401)."""

from uuid import UUID

from fastapi import APIRouter, Query

from openfinance.api.deps import ActorDep, BankAggregatorDep, UowDep
from openfinance.api.v1.schemas import (
    BankCompleteIn,
    BankConnectionOut,
    BankLinkIn,
    BankOut,
    BankRevokeOut,
    BankStartIn,
    BankStartOut,
)
from openfinance.application import bank
from openfinance.domain.shared.ids import AccountId
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["bank"])


@router.get("/bank", response_model=BankOut)
def get_bank(actor: ActorDep, uow: UowDep, aggregator: BankAggregatorDep) -> BankOut:
    now = utc_now()
    return BankOut(
        configured=aggregator.enabled,
        connections=[BankConnectionOut.of(c, now) for c in bank.list_connections(uow, actor, now)],
    )


@router.get("/bank/banks", response_model=list[str])
def list_banks(
    aggregator: BankAggregatorDep,
    _: ActorDep,
    country: str = Query(min_length=2, max_length=2, examples=["ES"]),
) -> list[str]:
    return bank.list_banks(aggregator, country)


@router.post("/bank/connections", response_model=BankStartOut, status_code=201)
def start_connection(
    body: BankStartIn, actor: ActorDep, uow: UowDep, aggregator: BankAggregatorDep
) -> BankStartOut:
    connection, url = bank.start_connection(
        uow, aggregator, actor, body.aspsp, body.country, utc_now()
    )
    return BankStartOut(connection_id=connection.id, url=url)


@router.post("/bank/connections/complete", response_model=BankConnectionOut)
def complete_connection(
    body: BankCompleteIn, actor: ActorDep, uow: UowDep, aggregator: BankAggregatorDep
) -> BankConnectionOut:
    connection = bank.complete_connection(uow, aggregator, actor, body.state, body.code)
    return BankConnectionOut.of(connection, utc_now())


@router.put("/bank/connections/{connection_id}/link", response_model=BankConnectionOut)
def link_account(
    connection_id: UUID, body: BankLinkIn, actor: ActorDep, uow: UowDep
) -> BankConnectionOut:
    now = utc_now()
    account = AccountId(body.account_id) if body.account_id else None
    connection = bank.link_account(uow, actor, connection_id, body.remote_uid, account, now)
    return BankConnectionOut.of(connection, now)


@router.post("/bank/connections/{connection_id}/revoke", response_model=BankRevokeOut)
def revoke_connection(
    connection_id: UUID, actor: ActorDep, uow: UowDep, aggregator: BankAggregatorDep
) -> BankRevokeOut:
    result = bank.revoke_connection(uow, aggregator, actor, connection_id)
    return BankRevokeOut(
        connection=BankConnectionOut.of(result.connection, utc_now()),
        closed_at_bank=result.closed_at_bank,
    )
