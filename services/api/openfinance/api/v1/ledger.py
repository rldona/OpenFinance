import base64
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    AccountOut,
    BulkCategorizeIn,
    BulkCategorizeOut,
    LinkIn,
    LinkOut,
    ManualTransactionIn,
    ManualTransactionOut,
    MoneyOut,
    OperationRefOut,
    SplitIn,
    SplitOut,
    TagOut,
    TagsIn,
    TagsOut,
    TransactionOut,
    TransactionPageOut,
)
from openfinance.application import ledger, links, movements, splits
from openfinance.application import tags as tags_app
from openfinance.application.decorate import decorate
from openfinance.application.ports import TransactionQuery, UnitOfWork
from openfinance.domain.categories import CategoryId
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.domain.workspaces import Actor
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
    tag: Annotated[str | None, Query(max_length=40, description="Solo con esta etiqueta")] = None,
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
            tag=tag or None,
            shared_only=shared_only,
            mine_only=mine_only,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    found = ledger.list_transactions(uow, actor, query)
    decor = decorate(uow, actor, found)
    return [TransactionOut.of(t, decor) for t in found]


def _encode_cursor(at: datetime, last_id: UUID) -> str:
    return base64.urlsafe_b64encode(f"{at.isoformat()}|{last_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        text = base64.urlsafe_b64decode(cursor.encode()).decode()
        at, last_id = text.split("|")
        return datetime.fromisoformat(at), UUID(last_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Cursor no válido") from exc


@router.get("/transactions/page", response_model=TransactionPageOut)
def page_transactions(
    actor: ActorDep,
    uow: UowDep,
    month: Annotated[str | None, Query(pattern=r"^(19|2\d)\d{2}-(0[1-9]|1[0-2])$")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    uncategorized: bool = False,
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    tag: Annotated[str | None, Query(max_length=40, description="Solo con esta etiqueta")] = None,
    cursor: Annotated[
        str | None, Query(max_length=200, description="`next_cursor` anterior")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TransactionPageOut:
    """Movimientos de 50 en 50 con el total del filtro (OF-803). Mismo orden que el listado."""
    year, mon = (int(month[:4]), int(month[5:])) if month else (None, None)
    try:
        query = TransactionQuery(
            year=year,
            month=mon,
            text=q or None,
            uncategorized=uncategorized,
            account_id=AccountId(account_id) if account_id else None,
            category_id=CategoryId(category_id) if category_id else None,
            tag=tag or None,
            limit=limit,
            after=_decode_cursor(cursor) if cursor else None,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    page = ledger.page_transactions(uow, actor, query)
    decor = decorate(uow, actor, page.items)
    return TransactionPageOut(
        items=[TransactionOut.of(t, decor) for t in page.items],
        next_cursor=_encode_cursor(*page.next_after) if page.next_after else None,
        count=page.count,
        total=MoneyOut.of(page.total),
    )


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
        transaction=TransactionOut.of(r.transaction, decorate(uow, actor, [r.transaction])),
        operation_id=r.operation_id,
    )


@router.delete("/transactions/{transaction_id}", response_model=OperationRefOut)
def delete_manual(transaction_id: UUID, actor: ActorDep, uow: UowDep) -> OperationRefOut:
    """Borra un movimiento manual: queda anulado y en el registro. Los importados no se borran."""
    op = movements.delete_manual(uow, actor, TransactionId(transaction_id), utc_now())
    return OperationRefOut(operation_id=op)


@router.get("/tags", response_model=list[TagOut])
def list_tags(actor: ActorDep, uow: UowDep) -> list[TagOut]:
    """Las etiquetas de los movimientos que ves, con cuántos las llevan."""
    return [TagOut(tag=t, count=n) for t, n in tags_app.list_tags(uow, actor)]


@router.put("/transactions/{transaction_id}/tags", response_model=TagsOut)
def set_tags(transaction_id: UUID, body: TagsIn, actor: ActorDep, uow: UowDep) -> TagsOut:
    """Sustituye las etiquetas de un movimiento; se puede deshacer."""
    result = tags_app.set_transaction_tags(
        uow, actor, TransactionId(transaction_id), body.tags, utc_now()
    )
    t = result.transaction
    return TagsOut(
        transaction=TransactionOut.of(t, decorate(uow, actor, [t])),
        operation_id=result.operation_id,
    )


@router.put("/transactions/{transaction_id}/split", response_model=SplitOut)
def split_transaction(
    transaction_id: UUID, body: SplitIn, actor: ActorDep, uow: UowDep
) -> SplitOut:
    """Divide un gasto en partes con categoría que suman su importe; se puede deshacer."""
    result = splits.split_transaction(
        uow,
        actor,
        TransactionId(transaction_id),
        [(p.amount.replace(",", "."), CategoryId(p.category_id)) for p in body.parts],
        utc_now(),
    )
    return SplitOut(
        transaction=TransactionOut.of(
            result.transaction, decorate(uow, actor, [result.transaction])
        ),
        operation_id=result.operation_id,
    )


@router.delete("/transactions/{transaction_id}/split", response_model=SplitOut)
def unsplit_transaction(transaction_id: UUID, actor: ActorDep, uow: UowDep) -> SplitOut:
    """Deshace la división de un gasto; se puede deshacer."""
    result = splits.unsplit_transaction(uow, actor, TransactionId(transaction_id), utc_now())
    return SplitOut(
        transaction=TransactionOut.of(
            result.transaction, decorate(uow, actor, [result.transaction])
        ),
        operation_id=result.operation_id,
    )


@router.get(
    "/transactions/{transaction_id}/transfer-candidates", response_model=list[TransactionOut]
)
def transfer_candidates(transaction_id: UUID, actor: ActorDep, uow: UowDep) -> list[TransactionOut]:
    """Posibles otros lados de un traspaso: importe contrario, otra cuenta tuya y pocos días."""
    found = links.candidates(uow, actor, TransactionId(transaction_id))
    decor = decorate(uow, actor, found)
    return [TransactionOut.of(t, decor) for t in found]


def _link_out(uow: UnitOfWork, actor: Actor, result: links.LinkResult) -> LinkOut:
    decor = decorate(uow, actor, [result.transaction, result.peer])
    return LinkOut(
        transaction=TransactionOut.of(result.transaction, decor),
        peer=TransactionOut.of(result.peer, decor),
        operation_id=result.operation_id,
    )


@router.put("/transactions/{transaction_id}/link", response_model=LinkOut)
def link_transfer(transaction_id: UUID, body: LinkIn, actor: ActorDep, uow: UowDep) -> LinkOut:
    """Enlaza los dos lados de un traspaso entre cuentas tuyas; se puede deshacer."""
    result = links.link_transfer(
        uow, actor, TransactionId(transaction_id), TransactionId(body.peer_id), utc_now()
    )
    return _link_out(uow, actor, result)


@router.delete("/transactions/{transaction_id}/link", response_model=LinkOut)
def unlink_transfer(transaction_id: UUID, actor: ActorDep, uow: UowDep) -> LinkOut:
    """Desenlaza un traspaso (los tipos no se tocan); se puede deshacer."""
    return _link_out(
        uow, actor, links.unlink_transfer(uow, actor, TransactionId(transaction_id), utc_now())
    )
