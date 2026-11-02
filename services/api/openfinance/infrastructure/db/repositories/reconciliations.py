"""Repositorio de comprobaciones de saldo (OF-1006)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from openfinance.domain.reconciliation import Reconciliation
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, UserId, WorkspaceId
from openfinance.infrastructure.db.models import ReconciliationRow
from openfinance.infrastructure.db.repositories._common import _as_utc, _flush


class SqlReconciliationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, reconciliation: Reconciliation) -> None:
        r = reconciliation
        self._s.add(
            ReconciliationRow(
                id=r.id,
                household_id=r.household_id,
                account_id=r.account_id,
                as_of=r.as_of,
                bank_balance=r.bank_balance.amount,
                computed_balance=r.computed_balance.amount,
                currency=r.bank_balance.currency.code,
                created_by=r.created_by,
            )
        )
        _flush(self._s)

    def for_account(
        self, household_id: WorkspaceId, account_id: AccountId, limit: int
    ) -> list[Reconciliation]:
        rows = self._s.scalars(
            select(ReconciliationRow)
            .where(
                ReconciliationRow.household_id == household_id,
                ReconciliationRow.account_id == account_id,
            )
            .order_by(ReconciliationRow.as_of.desc(), ReconciliationRow.created_at.desc())
            .limit(limit)
        )
        return [
            Reconciliation(
                r.id,
                WorkspaceId(r.household_id),
                AccountId(r.account_id),
                r.as_of,
                Money.of(r.bank_balance, r.currency),
                Money.of(r.computed_balance, r.currency),
                UserId(r.created_by),
                _as_utc(r.created_at),
            )
            for r in rows
        ]
