from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import AccountOut, TransactionOut
from openfinance.application import ledger
from openfinance.application.ports import TransactionQuery
from openfinance.domain.categories import CategoryId
from openfinance.domain.shared.ids import AccountId

router = APIRouter(tags=["ledger"])


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(actor: ActorDep, uow: UowDep) -> list[AccountOut]:
    return [AccountOut.of(v.account, v.balance) for v in ledger.list_accounts(uow, actor)]


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    actor: ActorDep,
    uow: UowDep,
    month: Annotated[str | None, Query(pattern=r"^(19|2\d)\d{2}-(0[1-9]|1[0-2])$")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    uncategorized: bool = False,
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    shared_only: Annotated[
        bool, Query(description="Solo cuentas del hogar (conjunta y huchas), como los gráficos")
    ] = False,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> list[TransactionOut]:
    year, mon = (int(month[:4]), int(month[5:])) if month else (None, None)
    try:
        query = TransactionQuery(
            year=year,
            month=mon,
            text=q or None,
            uncategorized=uncategorized,
            account_id=AccountId(account_id) if account_id else None,
            category_id=CategoryId(category_id) if category_id else None,
            shared_only=shared_only,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return [TransactionOut.of(t) for t in ledger.list_transactions(uow, actor, query)]
