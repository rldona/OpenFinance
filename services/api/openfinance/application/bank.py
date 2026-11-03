"""Conexión con el banco: consentimiento, cuentas enlazadas y revocación (ADR-0024, OF-1401).

Una conexión es de la persona que la creó: solo ella la ve, la enlaza, la sincroniza o la
revoca. Para cualquier otra persona, o de otro hogar, no existe (404).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from openfinance.application.errors import (
    AggregatorError,
    ApplicationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from openfinance.application.imports import (
    MAX_SOURCE,
    classification_rules,
    new_transaction,
    preview_rows,
)
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import BankAggregator, UnitOfWork
from openfinance.domain.bank import (
    MAX_ASPSP,
    SOURCE_PREFIX,
    BankConnection,
    BankError,
    BankLink,
    ConsentStatus,
    to_rows,
)
from openfinance.domain.imports import ParseResult
from openfinance.domain.imports.batch import ImportBatch
from openfinance.domain.ledger import Transaction
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.domain.workspaces import Actor

CONSENT_DAYS = 180
"""Lo máximo que PSD2 permite pedir; el agregador o el banco pueden dar menos."""
MAX_PENDING = 5
"""Conexiones sin terminar por persona: una persona no llena la tabla con intentos."""
MIN_MANUAL_INTERVAL = timedelta(minutes=5)
"""«Sincronizar ahora» no se puede lanzar en bucle: los bancos limitan las consultas."""
MIN_AUTO_INTERVAL = timedelta(hours=6)
"""Sin presencia de la persona PSD2 admite unas 4 consultas al día por cuenta (cron)."""
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


@dataclass(frozen=True, slots=True)
class LinkReport:
    remote_uid: str
    name: str
    created: int = 0
    duplicates: int = 0
    skipped: int = 0
    error: str = ""


@dataclass(frozen=True, slots=True)
class SyncReport:
    connection: BankConnection
    links: list[LinkReport] = field(default_factory=list)
    skipped_reason: str = ""
    """Por qué ni se intentó (caducada, demasiado pronto…); vacío si se sincronizó."""

    @property
    def created(self) -> int:
        return sum(r.created for r in self.links)

    @property
    def errors(self) -> list[str]:
        return [r.error for r in self.links if r.error]


def _sync_link(
    uow: UnitOfWork,
    aggregator: BankAggregator,
    actor: Actor,
    connection: BankConnection,
    link: BankLink,
    now: datetime,
) -> tuple[LinkReport, BankConnection]:
    """Trae y guarda los movimientos de una cuenta del banco. Nada se guarda si el banco falla."""
    accounts = {a.id: a for a in visible_accounts(uow, actor)}
    account = accounts.get(link.account_id) if link.account_id else None
    if account is None or connection.session_id is None:
        return LinkReport(
            link.remote_uid, link.name, error="La cuenta enlazada ya no está disponible"
        ), connection
    try:
        remote = aggregator.transactions(
            connection.session_id, link.remote_uid, connection.sync_start(now)
        )
    except AggregatorError as exc:
        return LinkReport(link.remote_uid, link.name, error=str(exc)), connection
    rules = classification_rules(
        account,
        uow.households.members(actor.household_id),
        uow.member_patterns.for_household(actor.household_id),
    )
    rows, skipped = to_rows(remote, rules, account.currency)
    reviewed = preview_rows(uow, actor, account, ParseResult(rows=rows))
    fresh = [r for r in reviewed if not r.duplicate]
    voided = uow.transactions.voided_with_fingerprints(
        actor.household_id, account.id, [r.row.fingerprint for r in fresh]
    )
    batch = ImportBatch(
        id=uuid4(),
        household_id=actor.household_id,
        account_id=account.id,
        filename=f"{SOURCE_PREFIX}{connection.aspsp} ····{link.iban_tail}"[:MAX_SOURCE],
        created_by=actor.user_id,
        created_at=now,
    )
    source = f"{SOURCE_PREFIX}{connection.aspsp}"[:MAX_SOURCE]
    created = 0
    new: list[Transaction] = []
    tagged: dict[TransactionId, tuple[str, ...]] = {}
    if fresh:
        uow.imports.add(batch, b"")  # antes que los movimientos: recuperar uno ya lo enlaza
    for r in fresh:
        previous = voided.get(r.row.fingerprint)
        if previous is not None:
            uow.transactions.save(replace(previous, voided=False, import_id=batch.id))
            created += 1
            continue
        transaction = new_transaction(actor, account, r, source, batch.id)
        new.append(transaction)
        if r.tags:
            tagged[transaction.id] = r.tags
        created += 1
    if fresh:
        uow.transactions.add_many(new)
        for transaction_id, tags in tagged.items():
            uow.tags.set(actor.household_id, transaction_id, tags)
        uow.imports.save_committed(batch.committed(now, created, len(reviewed) - created, skipped))
    updated = connection
    try:
        balance = aggregator.balance(connection.session_id, link.remote_uid)
    except AggregatorError:
        balance = None  # el saldo es un extra: sin él los movimientos valen igual
    if balance is not None:
        updated = connection.with_balance(link.remote_uid, balance)
    return (
        LinkReport(
            link.remote_uid,
            link.name,
            created=created,
            duplicates=len(reviewed) - len(fresh),
            skipped=skipped,
        ),
        updated,
    )


def sync_connection(
    uow: UnitOfWork,
    aggregator: BankAggregator,
    connection: BankConnection,
    now: datetime,
    *,
    min_interval: timedelta = MIN_MANUAL_INTERVAL,
) -> SyncReport:
    """Trae los movimientos nuevos de las cuentas enlazadas, con quien dio el consentimiento.

    Pasan por la misma tubería que un extracto: mismas huellas, reglas y comercios. Cada cuenta
    con novedades es un lote de importación que se puede deshacer. Si el banco falla, esa
    cuenta no cambia nada y el motivo queda en la conexión.
    """
    current = connection.current(now)
    if current.status is not ConsentStatus.ACTIVE:
        if current.status is not connection.status:
            uow.bank.save(current)
            uow.commit()
        return SyncReport(current, skipped_reason="El consentimiento ha caducado: conecta de nuevo")
    if current.last_sync_at is not None and now - current.last_sync_at < min_interval:
        return SyncReport(current, skipped_reason="Se sincronizó hace poco; inténtalo más tarde")
    actor = Actor(user_id=current.owner_id, household_id=current.household_id)
    reports: list[LinkReport] = []
    working = current
    for link in current.links:
        if link.account_id is None:
            continue
        report, working = _sync_link(uow, aggregator, actor, working, link, now)
        reports.append(report)
    errors = [r.error for r in reports if r.error]
    working = working.failed(errors[0]) if errors else working.synced(now)
    uow.bank.save(working)
    uow.commit()
    return SyncReport(working, reports)


def sync_owned(
    uow: UnitOfWork, aggregator: BankAggregator, actor: Actor, connection_id: UUID, now: datetime
) -> SyncReport:
    """«Sincronizar ahora»: solo la conexión de quien lo pide."""
    _enabled(aggregator)
    connection = _own(uow, actor, connection_id)
    if connection.status is ConsentStatus.REVOKED:
        raise ConflictError("Esta conexión está revocada")
    if connection.status is ConsentStatus.PENDING:
        raise ConflictError("Esta conexión aún no está autorizada")
    return sync_connection(uow, aggregator, connection, now)


def sync_all(uow: UnitOfWork, aggregator: BankAggregator, now: datetime) -> list[SyncReport]:
    """Todas las conexiones activas de todos los hogares (``openfinance bank sync``, cron).

    Una que falle no impide las demás. Respeta el límite de consultas diarias del banco.
    """
    reports: list[SyncReport] = []
    for connection in uow.bank.active():
        try:
            reports.append(
                sync_connection(uow, aggregator, connection, now, min_interval=MIN_AUTO_INTERVAL)
            )
        except ApplicationError as exc:
            reports.append(SyncReport(connection, skipped_reason=str(exc)))
    return reports
