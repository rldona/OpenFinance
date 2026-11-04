"""Revisar movimientos y comprobar el saldo contra el del banco (OF-1006)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from uuid import UUID, uuid4

from openfinance.application import changes as change_log
from openfinance.application.errors import InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.changes import Change, Entity
from openfinance.domain.ledger import Account
from openfinance.domain.reconciliation import Reconciliation
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.domain.workspaces import Actor

RECENT = 20


def set_reviewed(
    uow: UnitOfWork,
    actor: Actor,
    ids: list[TransactionId],
    reviewed: bool,
    now: datetime,
) -> tuple[int, UUID | None]:
    """Marca o desmarca movimientos como revisados. Solo los de cuentas que ve quien marca;
    el resto se ignora sin avisar (no se confirma que existan). Devuelve (cambiados, operación)."""
    visible = {a.id for a in visible_accounts(uow, actor)}
    changes: list[Change] = []
    for tid in dict.fromkeys(ids):
        t = uow.transactions.get(actor.household_id, tid)
        if t is None or t.account_id not in visible or t.reviewed == reviewed:
            continue
        uow.transactions.save(replace(t, reviewed=reviewed))
        changes.append(Change(Entity.TRANSACTION, str(t.id), "reviewed", t.reviewed, reviewed))
    label = "marcados como revisados" if reviewed else "marcados como sin revisar"
    operation = change_log.record(uow, actor, "transactions.review", label, changes, now)
    uow.commit()
    return len(changes), operation.id if operation else None


def _account(uow: UnitOfWork, actor: Actor, account_id: AccountId) -> Account:
    account = next((a for a in visible_accounts(uow, actor) if a.id == account_id), None)
    if account is None:
        raise NotFoundError("Cuenta no encontrada")
    return account


def reconcile(
    uow: UnitOfWork,
    actor: Actor,
    account_id: AccountId,
    as_of: date,
    bank_balance: str,
    now: datetime,
    today: date,
) -> Reconciliation:
    """Compara el saldo de la cuenta a ese día con el que da el banco y lo guarda."""
    account = _account(uow, actor, account_id)
    if as_of > today:
        raise InvalidRequestError("El saldo del banco no puede ser de una fecha futura")
    try:
        bank = Money.of(bank_balance, account.currency)
    except ValueError as exc:
        raise InvalidRequestError(f"Saldo no válido: {bank_balance}") from exc
    sums = uow.transactions.balances(
        actor.household_id, [account.id], until=datetime.combine(as_of, time.max)
    )
    computed = account.opening_balance + Money.of(sums.get(account.id, 0), account.currency)
    result = Reconciliation(
        uuid4(), actor.household_id, account.id, as_of, bank, computed, actor.user_id, now
    )
    uow.reconciliations.add(result)
    uow.commit()
    return result


def recent(uow: UnitOfWork, actor: Actor, account_id: AccountId) -> list[Reconciliation]:
    account = _account(uow, actor, account_id)
    return uow.reconciliations.for_account(actor.household_id, account.id, RECENT)
