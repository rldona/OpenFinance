"""Repositorio de las partes de un movimiento dividido (OF-1003)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.categories import CategoryId
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId, WorkspaceId
from openfinance.domain.splits import SplitPart
from openfinance.infrastructure.db.models import TransactionSplitRow
from openfinance.infrastructure.db.repositories._common import _flush


class SqlSplitRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_transactions(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, list[SplitPart]]:
        found: dict[TransactionId, list[SplitPart]] = {}
        for i in range(0, len(ids), 500):
            rows = self._s.scalars(
                select(TransactionSplitRow)
                .where(
                    TransactionSplitRow.household_id == household_id,
                    TransactionSplitRow.transaction_id.in_(ids[i : i + 500]),
                )
                .order_by(TransactionSplitRow.transaction_id, TransactionSplitRow.position)
            )
            for r in rows:
                found.setdefault(TransactionId(r.transaction_id), []).append(
                    SplitPart(Money.of(r.amount, r.currency), CategoryId(r.category_id))
                )
        return found

    def set(
        self, household_id: WorkspaceId, transaction_id: TransactionId, parts: list[SplitPart]
    ) -> None:
        self._s.execute(
            delete(TransactionSplitRow).where(
                TransactionSplitRow.household_id == household_id,
                TransactionSplitRow.transaction_id == transaction_id,
            )
        )
        self._s.add_all(
            TransactionSplitRow(
                transaction_id=transaction_id,
                position=i,
                household_id=household_id,
                amount=part.amount.amount,
                currency=part.amount.currency.code,
                category_id=part.category_id,
            )
            for i, part in enumerate(parts)
        )
        _flush(self._s)
