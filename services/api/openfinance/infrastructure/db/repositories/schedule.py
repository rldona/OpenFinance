"""Repositorio de pagos programados (OF-1201)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.categories import CategoryId
from openfinance.domain.schedule import Frequency, ScheduledPayment, ScheduleId
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, UserId, WorkspaceId
from openfinance.infrastructure.db.models import ScheduledPaymentRow
from openfinance.infrastructure.db.repositories._common import _flush


def _payment(row: ScheduledPaymentRow) -> ScheduledPayment:
    return ScheduledPayment(
        id=ScheduleId(row.id),
        household_id=WorkspaceId(row.household_id),
        name=row.name,
        amount=Money.of(row.amount, row.currency),
        account_id=AccountId(row.account_id),
        frequency=Frequency(row.frequency),
        first_due=row.first_due,
        interval=row.interval,
        ends_on=row.ends_on,
        category_id=CategoryId(row.category_id) if row.category_id else None,
        merchant=row.merchant,
        variable=row.variable,
        active=row.active,
    )


class SqlScheduleRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[ScheduledPayment]:
        rows = self._s.scalars(
            select(ScheduledPaymentRow)
            .where(ScheduledPaymentRow.household_id == household_id)
            .order_by(ScheduledPaymentRow.first_due, ScheduledPaymentRow.name)
        )
        return [_payment(r) for r in rows]

    def get(self, household_id: WorkspaceId, schedule_id: UUID) -> ScheduledPayment | None:
        row = self._s.scalar(
            select(ScheduledPaymentRow).where(
                ScheduledPaymentRow.id == schedule_id,
                ScheduledPaymentRow.household_id == household_id,
            )
        )
        return _payment(row) if row else None

    def save(self, payment: ScheduledPayment, created_by: UserId) -> None:
        row = self._s.get(ScheduledPaymentRow, payment.id)
        if row is None:
            row = ScheduledPaymentRow(
                id=payment.id, household_id=payment.household_id, created_by=created_by
            )
            self._s.add(row)
        row.account_id = payment.account_id
        row.name = payment.name
        row.amount = payment.amount.amount
        row.currency = payment.amount.currency.code
        row.frequency = payment.frequency.value
        row.interval = payment.interval
        row.first_due = payment.first_due
        row.ends_on = payment.ends_on
        row.category_id = payment.category_id
        row.merchant = payment.merchant
        row.variable = payment.variable
        row.active = payment.active
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, schedule_id: UUID) -> None:
        self._s.execute(
            delete(ScheduledPaymentRow).where(
                ScheduledPaymentRow.id == schedule_id,
                ScheduledPaymentRow.household_id == household_id,
            )
        )
        _flush(self._s)
