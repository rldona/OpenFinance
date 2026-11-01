"""Lo que se añade a un movimiento al enseñarlo: nombre del comercio, etiquetas y partes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from openfinance.application import merchants
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.ledger import Transaction
from openfinance.domain.shared.ids import TransactionId
from openfinance.domain.splits import SplitPart
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class Decor:
    names: dict[str, str] = field(default_factory=dict)
    """Nombre propio de cada variante de comercio (OF-1001)."""
    tags: dict[TransactionId, tuple[str, ...]] = field(default_factory=dict)
    """Etiquetas de cada movimiento (OF-1002)."""
    splits: dict[TransactionId, list[SplitPart]] = field(default_factory=dict)
    """Partes de cada movimiento dividido (OF-1003)."""
    peers: dict[TransactionId, TransactionId] = field(default_factory=dict)
    """El otro lado de cada traspaso enlazado, solo si quien mira también lo ve (OF-1004)."""


def decorate(uow: UnitOfWork, actor: Actor, transactions: Iterable[Transaction]) -> Decor:
    txns = list(transactions)
    ids = [t.id for t in txns]
    household_id = actor.household_id
    peers = uow.links.peers(household_id, ids)
    if peers:
        visible = {a.id for a in visible_accounts(uow, actor)}
        accounts = uow.transactions.accounts_of(household_id, list(set(peers.values())))
        peers = {t: p for t, p in peers.items() if accounts.get(p) in visible}
    return Decor(
        merchants.names_for(uow, household_id, txns),
        uow.tags.for_transactions(household_id, ids),
        uow.splits.for_transactions(household_id, ids),
        peers,
    )
