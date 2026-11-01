"""Lo que se añade a un movimiento al enseñarlo: nombre del comercio, etiquetas y partes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from openfinance.application import merchants
from openfinance.application.ports import UnitOfWork
from openfinance.domain.ledger import Transaction
from openfinance.domain.shared.ids import TransactionId, WorkspaceId
from openfinance.domain.splits import SplitPart


@dataclass(frozen=True, slots=True)
class Decor:
    names: dict[str, str] = field(default_factory=dict)
    """Nombre propio de cada variante de comercio (OF-1001)."""
    tags: dict[TransactionId, tuple[str, ...]] = field(default_factory=dict)
    """Etiquetas de cada movimiento (OF-1002)."""
    splits: dict[TransactionId, list[SplitPart]] = field(default_factory=dict)
    """Partes de cada movimiento dividido (OF-1003)."""


def decorate(
    uow: UnitOfWork, household_id: WorkspaceId, transactions: Iterable[Transaction]
) -> Decor:
    txns = list(transactions)
    ids = [t.id for t in txns]
    return Decor(
        merchants.names_for(uow, household_id, txns),
        uow.tags.for_transactions(household_id, ids),
        uow.splits.for_transactions(household_id, ids),
    )
