"""Repositorio de etiquetas de movimientos (OF-1002)."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from openfinance.domain.shared.ids import AccountId, TransactionId, WorkspaceId
from openfinance.domain.tags import tag_key
from openfinance.infrastructure.db.models import TransactionRow, TransactionTagRow
from openfinance.infrastructure.db.repositories._common import _flush


class SqlTagRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_transactions(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, tuple[str, ...]]:
        found: dict[TransactionId, list[str]] = {}
        for i in range(0, len(ids), 500):
            rows = self._s.execute(
                select(TransactionTagRow.transaction_id, TransactionTagRow.tag)
                .where(
                    TransactionTagRow.household_id == household_id,
                    TransactionTagRow.transaction_id.in_(ids[i : i + 500]),
                )
                .order_by(TransactionTagRow.tag_key)
            )
            for transaction_id, tag in rows:
                found.setdefault(TransactionId(transaction_id), []).append(tag)
        return {k: tuple(v) for k, v in found.items()}

    def set(
        self, household_id: WorkspaceId, transaction_id: TransactionId, tags: tuple[str, ...]
    ) -> None:
        self._s.execute(
            delete(TransactionTagRow).where(
                TransactionTagRow.household_id == household_id,
                TransactionTagRow.transaction_id == transaction_id,
            )
        )
        self._s.add_all(
            TransactionTagRow(
                transaction_id=transaction_id,
                tag_key=tag_key(tag),
                household_id=household_id,
                tag=tag,
            )
            for tag in tags
        )
        _flush(self._s)

    def counts(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> list[tuple[str, int]]:
        if not account_ids:
            return []
        rows = self._s.execute(
            select(func.min(TransactionTagRow.tag), func.count())
            .join(TransactionRow, TransactionRow.id == TransactionTagRow.transaction_id)
            .where(
                TransactionTagRow.household_id == household_id,
                TransactionRow.account_id.in_(account_ids),
                TransactionRow.voided.is_(False),
            )
            .group_by(TransactionTagRow.tag_key)
            .order_by(TransactionTagRow.tag_key)
        )
        return [(tag, int(n)) for tag, n in rows]
