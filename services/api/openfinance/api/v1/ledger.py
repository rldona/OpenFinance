from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    AccountOut,
    BulkCategorizeIn,
    BulkCategorizeOut,
    ManualTransactionIn,
    ManualTransactionOut,
    OperationRefOut,
    TransactionOut,
)
from openfinance.application import ledger, movements
from openfinance.application.ports import TransactionQuery
from openfinance.domain.categories import CategoryId
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.infrastructure.time import utc_now

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
    mine_only: Annotated[
        bool, Query(description="Solo tus cuentas personales, como la vista «mío»")
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
            mine_only=mine_only,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return [TransactionOut.of(t) for t in ledger.list_transactions(uow, actor, query)]


@router.post("/transactions/categorize", response_model=BulkCategorizeOut)
def categorize_many(body: BulkCategorizeIn, actor: ActorDep, uow: UowDep) -> BulkCategorizeOut:
    """Pone la misma categoría a varios gastos, sin aprender reglas, en una sola operación."""
    r = movements.categorize_many(
        uow,
        actor,
        [TransactionId(i) for i in body.ids],
        CategoryId(body.category_id) if body.category_id else None,
        utc_now(),
    )
    return BulkCategorizeOut(updated=r.updated, operation_id=r.operation_id)


@router.post(
    "/transactions", response_model=ManualTransactionOut, status_code=status.HTTP_201_CREATED
)
def add_manual(body: ManualTransactionIn, actor: ActorDep, uow: UowDep) -> ManualTransactionOut:
    """Añade a mano un gasto o un ingreso (p. ej. en efectivo). Se puede deshacer y borrar."""
    r = movements.add_manual(
        uow,
        actor,
        movements.NewManual(
            account_id=AccountId(body.account_id),
            booked_on=body.booked_on,
            description=body.description,
            amount=body.amount,
            kind=body.kind,
            category_id=CategoryId(body.category_id) if body.category_id else None,
            note=body.note,
        ),
        utc_now(),
    )
    return ManualTransactionOut(
        transaction=TransactionOut.of(r.transaction), operation_id=r.operation_id
    )


@router.delete("/transactions/{transaction_id}", response_model=OperationRefOut)
def delete_manual(transaction_id: UUID, actor: ActorDep, uow: UowDep) -> OperationRefOut:
    """Borra un movimiento manual: queda anulado y en el registro. Los importados no se borran."""
    op = movements.delete_manual(uow, actor, TransactionId(transaction_id), utc_now())
    return OperationRefOut(operation_id=op)
