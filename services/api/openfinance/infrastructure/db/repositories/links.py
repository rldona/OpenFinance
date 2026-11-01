"""Repositorio de traspasos enlazados (OF-1004)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.shared.ids import TransactionId, WorkspaceId
from openfinance.infrastructure.db.models import TransactionLinkRow
from openfinance.infrastructure.db.repositories._common import _flush


class SqlLinkRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def peers(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, TransactionId]:
        found: dict[TransactionId, TransactionId] = {}
        for i in range(0, len(ids), 500):
            rows = self._s.execute(
                select(TransactionLinkRow.transaction_id, TransactionLinkRow.peer_id).where(
                    TransactionLinkRow.household_id == household_id,
                    TransactionLinkRow.transaction_id.in_(ids[i : i + 500]),
                )
            )
            found.update({TransactionId(a): TransactionId(b) for a, b in rows})
        return found

    def link(self, household_id: WorkspaceId, a: TransactionId, b: TransactionId) -> None:
        self._s.add_all(
            [
                TransactionLinkRow(transaction_id=a, peer_id=b, household_id=household_id),
                TransactionLinkRow(transaction_id=b, peer_id=a, household_id=household_id),
            ]
        )
        _flush(self._s)

    def unlink(self, household_id: WorkspaceId, a: TransactionId) -> None:
        peer = self.peers(household_id, [a]).get(a)
        ids = [a] if peer is None else [a, peer]
        self._s.execute(
            delete(TransactionLinkRow).where(
                TransactionLinkRow.household_id == household_id,
                TransactionLinkRow.transaction_id.in_(ids),
            )
        )
        _flush(self._s)
