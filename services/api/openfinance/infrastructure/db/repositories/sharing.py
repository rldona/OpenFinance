"""Repositorio del reparto de gastos (ADR-0026, OF-1602)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import UserId, WorkspaceId
from openfinance.domain.sharing import (
    Event,
    Guest,
    Settlement,
    SettlementStatus,
    SharedExpense,
    SplitMethod,
)
from openfinance.infrastructure.db.models import (
    EventRow,
    GuestRow,
    SettlementRow,
    SharedExpensePartRow,
    SharedExpensePayerRow,
    SharedExpenseRow,
)
from openfinance.infrastructure.db.repositories._common import _as_utc, _flush


def _guest(row: GuestRow) -> Guest:
    return Guest(row.id, WorkspaceId(row.household_id), row.name, row.archived)


def _event(row: EventRow) -> Event:
    return Event(
        id=row.id,
        household_id=WorkspaceId(row.household_id),
        name=row.name,
        created_at=_as_utc(row.created_at),
        icon=row.icon,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        closed=row.closed,
    )


def _settlement(row: SettlementRow) -> Settlement:
    return Settlement(
        id=row.id,
        household_id=WorkspaceId(row.household_id),
        from_id=row.from_id,
        to_id=row.to_id,
        amount=Money.of(row.amount, Currency(row.currency)),
        on=row.on_date,
        created_by=UserId(row.created_by),
        created_at=_as_utc(row.created_at),
        status=SettlementStatus(row.status),
        reference=row.reference,
        confirmed_by=UserId(row.confirmed_by) if row.confirmed_by else None,
        confirmed_at=_as_utc(row.confirmed_at) if row.confirmed_at else None,
    )


class SqlSharingRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    # --- invitados ---
    def guests(self, household_id: WorkspaceId) -> list[Guest]:
        rows = self._s.scalars(
            select(GuestRow)
            .where(GuestRow.household_id == household_id)
            .order_by(GuestRow.name, GuestRow.id)
        )
        return [_guest(r) for r in rows]

    def get_guest(self, household_id: WorkspaceId, guest_id: UUID) -> Guest | None:
        row = self._s.scalar(
            select(GuestRow).where(GuestRow.household_id == household_id, GuestRow.id == guest_id)
        )
        return _guest(row) if row else None

    def add_guest(self, guest: Guest) -> None:
        self._s.add(
            GuestRow(
                id=guest.id,
                household_id=guest.household_id,
                name=guest.name,
                archived=guest.archived,
            )
        )
        _flush(self._s)

    def save_guest(self, guest: Guest) -> None:
        row = self._s.get(GuestRow, guest.id)
        if row is None:
            raise LookupError(guest.id)
        row.name = guest.name
        row.archived = guest.archived
        _flush(self._s)

    # --- gastos ---
    def _expense(self, row: SharedExpenseRow) -> SharedExpense:
        currency = Currency(row.currency)
        payers = self._s.execute(
            select(SharedExpensePayerRow.participant_id, SharedExpensePayerRow.amount)
            .where(SharedExpensePayerRow.expense_id == row.id)
            .order_by(SharedExpensePayerRow.participant_id)
        )
        parts = self._s.execute(
            select(SharedExpensePartRow.participant_id, SharedExpensePartRow.amount)
            .where(SharedExpensePartRow.expense_id == row.id)
            .order_by(SharedExpensePartRow.participant_id)
        )
        return SharedExpense(
            id=row.id,
            household_id=WorkspaceId(row.household_id),
            on=row.on_date,
            description=row.description,
            amount=Money.of(row.amount, currency),
            payers=tuple((p, Money.of(a, currency)) for p, a in payers),
            method=SplitMethod(row.method),
            parts=tuple((p, Money.of(a, currency)) for p, a in parts),
            created_by=UserId(row.created_by),
            created_at=_as_utc(row.created_at),
            category_id=row.category_id,
            event_id=row.event_id,
            voided=row.voided,
        )

    def _write_children(self, expense: SharedExpense) -> None:
        self._s.execute(
            delete(SharedExpensePayerRow).where(SharedExpensePayerRow.expense_id == expense.id)
        )
        self._s.execute(
            delete(SharedExpensePartRow).where(SharedExpensePartRow.expense_id == expense.id)
        )
        _flush(self._s)
        for who, money in expense.payers:
            self._s.add(
                SharedExpensePayerRow(
                    expense_id=expense.id, participant_id=who, amount=money.amount
                )
            )
        for who, money in expense.parts:
            self._s.add(
                SharedExpensePartRow(expense_id=expense.id, participant_id=who, amount=money.amount)
            )
        _flush(self._s)

    def add_expense(self, expense: SharedExpense) -> None:
        self._s.add(
            SharedExpenseRow(
                id=expense.id,
                household_id=expense.household_id,
                on_date=expense.on,
                description=expense.description.strip(),
                amount=expense.amount.amount,
                currency=expense.amount.currency.code,
                method=expense.method.value,
                category_id=expense.category_id,
                event_id=expense.event_id,
                created_by=expense.created_by,
                created_at=expense.created_at,
                voided=expense.voided,
            )
        )
        _flush(self._s)
        self._write_children(expense)

    def save_expense(self, expense: SharedExpense) -> None:
        row = self._s.get(SharedExpenseRow, expense.id)
        if row is None:
            raise LookupError(expense.id)
        row.on_date = expense.on
        row.description = expense.description.strip()
        row.amount = expense.amount.amount
        row.method = expense.method.value
        row.category_id = expense.category_id
        row.event_id = expense.event_id
        row.voided = expense.voided
        _flush(self._s)
        self._write_children(expense)

    def get_expense(self, household_id: WorkspaceId, expense_id: UUID) -> SharedExpense | None:
        row = self._s.scalar(
            select(SharedExpenseRow).where(
                SharedExpenseRow.household_id == household_id, SharedExpenseRow.id == expense_id
            )
        )
        return self._expense(row) if row else None

    def expenses(self, household_id: WorkspaceId) -> list[SharedExpense]:
        rows = self._s.scalars(
            select(SharedExpenseRow)
            .where(SharedExpenseRow.household_id == household_id)
            .order_by(
                SharedExpenseRow.on_date.desc(),
                SharedExpenseRow.created_at.desc(),
                SharedExpenseRow.id,
            )
        )
        return [self._expense(r) for r in rows]

    # --- eventos ---
    def events(self, household_id: WorkspaceId) -> list[Event]:
        rows = self._s.scalars(
            select(EventRow)
            .where(EventRow.household_id == household_id)
            .order_by(EventRow.created_at.desc(), EventRow.id)
        )
        return [_event(r) for r in rows]

    def get_event(self, household_id: WorkspaceId, event_id: UUID) -> Event | None:
        row = self._s.scalar(
            select(EventRow).where(EventRow.household_id == household_id, EventRow.id == event_id)
        )
        return _event(row) if row else None

    def add_event(self, event: Event) -> None:
        self._s.add(
            EventRow(
                id=event.id,
                household_id=event.household_id,
                name=event.name.strip(),
                icon=event.icon,
                starts_on=event.starts_on,
                ends_on=event.ends_on,
                closed=event.closed,
                created_at=event.created_at,
            )
        )
        _flush(self._s)

    def save_event(self, event: Event) -> None:
        row = self._s.get(EventRow, event.id)
        if row is None:
            raise LookupError(event.id)
        row.name = event.name.strip()
        row.icon = event.icon
        row.starts_on = event.starts_on
        row.ends_on = event.ends_on
        row.closed = event.closed
        _flush(self._s)

    def delete_event(self, household_id: WorkspaceId, event_id: UUID) -> None:
        self._s.execute(
            delete(EventRow).where(EventRow.household_id == household_id, EventRow.id == event_id)
        )
        _flush(self._s)

    def event_expense_count(self, household_id: WorkspaceId, event_id: UUID) -> int:
        """Los gastos que apuntan al evento, también los anulados."""
        return int(
            self._s.scalar(
                select(func.count())
                .select_from(SharedExpenseRow)
                .where(
                    SharedExpenseRow.household_id == household_id,
                    SharedExpenseRow.event_id == event_id,
                )
            )
            or 0
        )

    # --- liquidaciones ---
    def add_settlement(self, s: Settlement) -> None:
        self._s.add(
            SettlementRow(
                id=s.id,
                household_id=s.household_id,
                from_id=s.from_id,
                to_id=s.to_id,
                amount=s.amount.amount,
                currency=s.amount.currency.code,
                on_date=s.on,
                status=s.status.value,
                reference=s.reference,
                created_by=s.created_by,
                created_at=s.created_at,
            )
        )
        _flush(self._s)

    def save_settlement(self, s: Settlement) -> None:
        row = self._s.get(SettlementRow, s.id)
        if row is None:
            raise LookupError(s.id)
        row.status = s.status.value
        row.confirmed_by = s.confirmed_by
        row.confirmed_at = s.confirmed_at
        _flush(self._s)

    def get_settlement(self, household_id: WorkspaceId, settlement_id: UUID) -> Settlement | None:
        row = self._s.scalar(
            select(SettlementRow).where(
                SettlementRow.household_id == household_id, SettlementRow.id == settlement_id
            )
        )
        return _settlement(row) if row else None

    def settlement_by_reference(
        self, household_id: WorkspaceId, reference: str
    ) -> Settlement | None:
        row = self._s.scalar(
            select(SettlementRow).where(
                SettlementRow.household_id == household_id, SettlementRow.reference == reference
            )
        )
        return _settlement(row) if row else None

    def settlements(self, household_id: WorkspaceId) -> list[Settlement]:
        rows = self._s.scalars(
            select(SettlementRow)
            .where(SettlementRow.household_id == household_id)
            .order_by(
                SettlementRow.on_date.desc(), SettlementRow.created_at.desc(), SettlementRow.id
            )
        )
        return [_settlement(r) for r in rows]
