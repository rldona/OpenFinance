from uuid import UUID

from fastapi import APIRouter

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import ChangeOut, OperationOut, RevertOut
from openfinance.application import changes
from openfinance.domain.changes import Change, Operation
from openfinance.domain.shared.ids import TransactionId
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["changes"])


def _operation(
    o: Operation, only: list[Change] | None = None, summary: str | None = None
) -> OperationOut:
    return OperationOut(
        id=o.id,
        actor_id=o.actor_id,
        created_at=o.created_at,
        action=o.action,
        summary=summary if summary is not None else changes.display_summary(o),
        undone=o.is_undone,
        changes=[
            ChangeOut(entity=c.entity.value, field=c.field, before=c.before, after=c.after)
            for c in (o.changes if only is None else only)
        ],
    )


def _revert(r: changes.RevertResult) -> RevertOut:
    return RevertOut(
        operation=_operation(r.operation), applied=r.applied, kept=r.kept, kept_by=r.kept_by
    )


@router.get("/changes", response_model=list[OperationOut])
def recent(actor: ActorDep, uow: UowDep) -> list[OperationOut]:
    """Tus últimas operaciones (nunca las de otra persona), de la más reciente a la más antigua."""
    return [_operation(o) for o in changes.recent_operations(uow, actor)]


@router.post("/changes/{operation_id}/undo", response_model=RevertOut)
def undo(operation_id: UUID, actor: ActorDep, uow: UowDep) -> RevertOut:
    """Deshace una operación tuya. Lo que alguien cambió después no se toca."""
    return _revert(changes.undo(uow, actor, operation_id, utc_now()))


@router.post("/changes/{operation_id}/redo", response_model=RevertOut)
def redo(operation_id: UUID, actor: ActorDep, uow: UowDep) -> RevertOut:
    return _revert(changes.redo(uow, actor, operation_id, utc_now()))


@router.get("/transactions/{transaction_id}/history", response_model=list[OperationOut])
def history(transaction_id: UUID, actor: ActorDep, uow: UowDep) -> list[OperationOut]:
    """Correcciones de un movimiento, de cualquier persona, de la más antigua a la más reciente."""
    items = changes.transaction_history(uow, actor, TransactionId(transaction_id))
    return [_operation(i.operation, i.changes, i.summary) for i in items]
