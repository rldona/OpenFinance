"""Reparto de gastos del hogar (ADR-0026, OF-1602)."""

from uuid import UUID

from fastapi import APIRouter, Response, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    AmountOfOut,
    BalanceOut,
    BalancesOut,
    ExpenseIn,
    ExpenseOut,
    GuestIn,
    MoneyOut,
    ParticipantOut,
    SettlementIn,
    SettlementOut,
    ShareIn,
    SplitPreviewIn,
    TransferOut,
)
from openfinance.application import sharing
from openfinance.application.errors import InvalidRequestError
from openfinance.domain.sharing import Settlement, SharedExpense, SplitMethod
from openfinance.infrastructure.time import utc_now

router = APIRouter(prefix="/sharing", tags=["sharing"])


def _participant(p: sharing.Participant) -> ParticipantOut:
    return ParticipantOut(id=p.id, name=p.name, is_guest=p.is_guest, active=p.active)


def _expense(e: SharedExpense) -> ExpenseOut:
    return ExpenseOut(
        id=e.id,
        on=e.on,
        description=e.description,
        amount=MoneyOut.of(e.amount),
        method=e.method.value,
        payers=[AmountOfOut(participant_id=p, amount=MoneyOut.of(m)) for p, m in e.payers],
        parts=[AmountOfOut(participant_id=p, amount=MoneyOut.of(m)) for p, m in e.parts],
        category_id=e.category_id,
        created_by=e.created_by,
        voided=e.voided,
    )


def _settlement(s: Settlement) -> SettlementOut:
    return SettlementOut(
        id=s.id,
        from_id=s.from_id,
        to_id=s.to_id,
        amount=MoneyOut.of(s.amount),
        on=s.on,
        status=s.status.value,
        reference=s.reference,
        created_by=s.created_by,
        confirmed_by=s.confirmed_by,
    )


def _shares(items: list[ShareIn]) -> dict[UUID, str]:
    # Un participante repetido se rechaza en el dominio, no se pisa en silencio.
    out: dict[UUID, str] = {}
    for item in items:
        if item.participant_id in out:
            raise InvalidRequestError("Hay participantes repetidos")
        out[item.participant_id] = item.value or "0"
    return out


@router.get("/participants", response_model=list[ParticipantOut])
def list_participants(actor: ActorDep, uow: UowDep) -> list[ParticipantOut]:
    return [_participant(p) for p in sharing.participants(uow, actor)]


@router.post("/guests", response_model=ParticipantOut, status_code=status.HTTP_201_CREATED)
def add_guest(body: GuestIn, actor: ActorDep, uow: UowDep) -> ParticipantOut:
    guest = sharing.add_guest(uow, actor, body.name)
    return ParticipantOut(id=guest.id, name=guest.name, is_guest=True, active=True)


@router.post("/guests/{guest_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_guest(guest_id: UUID, actor: ActorDep, uow: UowDep) -> Response:
    sharing.archive_guest(uow, actor, guest_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/split-preview", response_model=list[AmountOfOut])
def preview(body: SplitPreviewIn, actor: ActorDep, uow: UowDep) -> list[AmountOfOut]:
    parts = sharing.preview_split(
        uow, actor, body.amount, SplitMethod(body.method), _shares(body.shares)
    )
    return [AmountOfOut(participant_id=p, amount=MoneyOut.of(m)) for p, m in parts.items()]


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(actor: ActorDep, uow: UowDep) -> list[ExpenseOut]:
    return [_expense(e) for e in sharing.list_expenses(uow, actor)]


@router.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(body: ExpenseIn, actor: ActorDep, uow: UowDep) -> ExpenseOut:
    expense = sharing.create_expense(
        uow,
        actor,
        body.on,
        body.description,
        body.amount,
        {p.participant_id: p.amount for p in body.payers},
        SplitMethod(body.method),
        _shares(body.shares),
        body.category_id,
        utc_now(),
    )
    return _expense(expense)


@router.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: UUID, body: ExpenseIn, actor: ActorDep, uow: UowDep) -> ExpenseOut:
    expense = sharing.update_expense(
        uow,
        actor,
        expense_id,
        body.on,
        body.description,
        body.amount,
        {p.participant_id: p.amount for p in body.payers},
        SplitMethod(body.method),
        _shares(body.shares),
        body.category_id,
    )
    return _expense(expense)


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def void_expense(expense_id: UUID, actor: ActorDep, uow: UowDep) -> Response:
    sharing.void_expense(uow, actor, expense_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/balances", response_model=BalancesOut)
def get_balances(actor: ActorDep, uow: UowDep) -> BalancesOut:
    view = sharing.balance_view(uow, actor)
    return BalancesOut(
        balances=[
            BalanceOut(
                participant=_participant(p),
                paid=MoneyOut.of(b.paid),
                share=MoneyOut.of(b.share),
                settled=MoneyOut.of(b.settled),
                net=MoneyOut.of(b.net),
            )
            for p, b in view.balances
        ],
        suggestions=[
            TransferOut(from_id=t.from_id, to_id=t.to_id, amount=MoneyOut.of(t.amount))
            for t in view.suggestions
        ],
    )


@router.get("/settlements", response_model=list[SettlementOut])
def list_settlements(actor: ActorDep, uow: UowDep) -> list[SettlementOut]:
    return [_settlement(s) for s in sharing.list_settlements(uow, actor)]


@router.post("/settlements", response_model=SettlementOut, status_code=status.HTTP_201_CREATED)
def create_settlement(
    body: SettlementIn, response: Response, actor: ActorDep, uow: UowDep
) -> SettlementOut:
    settlement, created = sharing.create_settlement(
        uow, actor, body.from_id, body.to_id, body.amount, body.on, body.reference, utc_now()
    )
    if not created:
        response.status_code = status.HTTP_200_OK  # la misma referencia: ya estaba registrada
    return _settlement(settlement)


@router.post("/settlements/{settlement_id}/confirm", response_model=SettlementOut)
def confirm_settlement(settlement_id: UUID, actor: ActorDep, uow: UowDep) -> SettlementOut:
    return _settlement(sharing.confirm_settlement(uow, actor, settlement_id, utc_now()))


@router.post("/settlements/{settlement_id}/cancel", response_model=SettlementOut)
def cancel_settlement(settlement_id: UUID, actor: ActorDep, uow: UowDep) -> SettlementOut:
    return _settlement(sharing.cancel_settlement(uow, actor, settlement_id))
