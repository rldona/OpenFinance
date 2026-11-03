"""Conexión con el banco: consentimiento, cuentas enlazadas y revocación (ADR-0024, OF-1401).

Una conexión es de la persona que la creó: solo ella la ve, la enlaza, la sincroniza o la
revoca. Para cualquier otra persona, o de otro hogar, no existe (404).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from openfinance.application.errors import AggregatorError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import BankAggregator, UnitOfWork
from openfinance.domain.bank import (
    MAX_ASPSP,
    BankConnection,
    BankError,
    ConsentStatus,
)
from openfinance.domain.shared.ids import AccountId
from openfinance.domain.workspaces import Actor

CONSENT_DAYS = 180
"""Lo máximo que PSD2 permite pedir; el agregador o el banco pueden dar menos."""
MAX_PENDING = 5
"""Conexiones sin terminar por persona: una persona no llena la tabla con intentos."""
_COUNTRY = re.compile(r"^[A-Z]{2}$")


def _clean_bank(aspsp: str, country: str) -> tuple[str, str]:
    name = " ".join(aspsp.split())
    code = country.strip().upper()
    if not name or len(name) > MAX_ASPSP or not name.isprintable():
        raise InvalidRequestError("Indica el nombre del banco")
    if not _COUNTRY.match(code):
        raise InvalidRequestError("El país son dos letras, por ejemplo ES")
    return name, code


def _enabled(aggregator: BankAggregator) -> None:
    if not aggregator.enabled:
        raise InvalidRequestError("La conexión con el banco no está configurada en este servidor")


def _own(uow: UnitOfWork, actor: Actor, connection_id: UUID) -> BankConnection:
    connection = uow.bank.get(actor.household_id, connection_id)
    if connection is None or connection.owner_id != actor.user_id:
        raise NotFoundError("Conexión no encontrada")
    return connection


def list_banks(aggregator: BankAggregator, country: str) -> list[str]:
    _enabled(aggregator)
    _, code = _clean_bank("x", country)
    return aggregator.banks(code)


def list_connections(uow: UnitOfWork, actor: Actor, now: datetime) -> list[BankConnection]:
    """Las conexiones de quien pregunta, con el estado al día (una activa vencida es caducada)."""
    return [c.current(now) for c in uow.bank.for_owner(actor.household_id, actor.user_id)]


def start_connection(
    uow: UnitOfWork,
    aggregator: BankAggregator,
    actor: Actor,
    aspsp: str,
    country: str,
    now: datetime,
) -> tuple[BankConnection, str]:
    """Crea la conexión pendiente y devuelve la dirección del banco donde se autoriza."""
    _enabled(aggregator)
    name, code = _clean_bank(aspsp, country)
    pending = [
        c
        for c in uow.bank.for_owner(actor.household_id, actor.user_id)
        if c.status is ConsentStatus.PENDING
    ]
    if len(pending) >= MAX_PENDING:
        raise InvalidRequestError("Tienes demasiadas conexiones sin terminar; revoca alguna")
    state = secrets.token_urlsafe(32)
    url = aggregator.start(name, code, state, now + timedelta(days=CONSENT_DAYS))
    connection = BankConnection(
        id=uuid4(),
        household_id=actor.household_id,
        owner_id=actor.user_id,
        aspsp=name,
        country=code,
        status=ConsentStatus.PENDING,
        created_at=now,
        state=state,
    )
    uow.bank.add(connection)
    uow.commit()
    return connection, url


def complete_connection(
    uow: UnitOfWork, aggregator: BankAggregator, actor: Actor, state: str, code: str
) -> BankConnection:
    """Cierra el consentimiento con lo que trae la vuelta del banco.

    El ``state`` tiene que ser de una conexión pendiente de quien tiene la sesión: otra
    persona que lo conozca no puede completarla.
    """
    _enabled(aggregator)
    connection = uow.bank.by_state(state)
    if (
        connection is None
        or connection.owner_id != actor.user_id
        or connection.household_id != actor.household_id
    ):
        raise NotFoundError("Conexión no encontrada")
    try:
        session_id, accounts, valid_until = aggregator.authorize(code)
    except AggregatorError:
        # El código es de un solo uso: la conexión no se puede reintentar con el mismo.
        uow.bank.save(connection.revoked())
        uow.commit()
        raise
    uow.bank.save(connection.activate(session_id, accounts, valid_until))
    uow.commit()
    saved = uow.bank.get(actor.household_id, connection.id)
    assert saved is not None
    return saved


def link_account(
    uow: UnitOfWork,
    actor: Actor,
    connection_id: UUID,
    remote_uid: str,
    account_id: AccountId | None,
    now: datetime,
) -> BankConnection:
    """Elige a qué cuenta del hogar alimenta una cuenta del banco (``None`` la desenlaza).

    Solo cuentas que la persona ve (ADR-0013) y de la misma moneda.
    """
    connection = _own(uow, actor, connection_id).current(now)
    link = next((x for x in connection.links if x.remote_uid == remote_uid), None)
    if link is None:
        raise NotFoundError("Cuenta del banco no encontrada")
    if account_id is not None:
        account = next((a for a in visible_accounts(uow, actor) if a.id == account_id), None)
        if account is None:
            raise NotFoundError("Cuenta no encontrada")
        if account.currency.code != link.currency:
            raise InvalidRequestError("La cuenta y la del banco tienen monedas distintas")
        if uow.bank.linked_to(actor.household_id, account.id) and not any(
            x.account_id == account.id for x in connection.links
        ):
            raise InvalidRequestError("Esa cuenta ya recibe movimientos de otra conexión")
    try:
        updated = connection.link_to(remote_uid, account_id)
    except BankError as exc:
        raise InvalidRequestError(str(exc)) from exc
    uow.bank.save(updated)
    uow.commit()
    return updated


@dataclass(frozen=True, slots=True)
class RevokeResult:
    connection: BankConnection
    closed_at_bank: bool
    """Si el agregador cerró la sesión; si no, el consentimiento caduca solo en el banco."""


def revoke_connection(
    uow: UnitOfWork, aggregator: BankAggregator, actor: Actor, connection_id: UUID
) -> RevokeResult:
    """Detiene la sincronización y pide al agregador cerrar la sesión. No borra movimientos."""
    connection = _own(uow, actor, connection_id)
    if connection.status is ConsentStatus.REVOKED:
        return RevokeResult(connection, True)
    closed = connection.session_id is None
    if connection.session_id is not None and aggregator.enabled:
        try:
            aggregator.revoke(connection.session_id)
            closed = True
        except AggregatorError:
            closed = False
    revoked = connection.revoked()
    uow.bank.save(revoked)
    uow.commit()
    return RevokeResult(revoked, closed)
