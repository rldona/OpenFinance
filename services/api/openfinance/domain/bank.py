"""Conexión con el banco mediante un agregador PSD2 (ADR-0024, OF-1401..1404).

Aquí vive lo que no depende del agregador: la conexión y su consentimiento, las cuentas del
banco enlazadas con las del hogar, cómo se convierte un movimiento del banco en una fila de
extracto y cómo se concilia con lo que ya estaba anotado.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from openfinance.domain.imports import (
    ClassificationRules,
    ImportedRow,
    suggest_kind,
)
from openfinance.domain.ledger import Transaction
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, UserId, WorkspaceId

FIRST_SYNC_DAYS = 90
"""La primera vez se pide como mucho este historial."""
OVERLAP_DAYS = 7
"""Después se pide desde unos días antes: los bancos corrigen fechas con retraso."""
RECONCILE_DAYS = 3
"""Un movimiento anotado concilia con uno del banco si difiere como mucho estos días."""
EXPIRY_WARNING_DAYS = 14
SOURCE_PREFIX = "banco:"
"""Procedencia de los movimientos que vienen del banco (o conciliados con él)."""
MAX_ERROR = 300
MAX_ASPSP = 100


class BankError(ValueError):
    """Una operación que la conexión no admite (estado, enlace, datos)."""


class ConsentStatus(StrEnum):
    PENDING = "pending"
    """Creada; falta que la persona autorice en el banco."""
    ACTIVE = "active"
    EXPIRED = "expired"
    """Pasó la fecha del consentimiento: no se sincroniza hasta renovarlo."""
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class BankAccountRef:
    """Una cuenta que la persona ha autorizado en el banco."""

    uid: str
    """Identificador que usa el agregador mientras dura la sesión."""
    iban_tail: str
    """Últimos cuatro caracteres del IBAN: lo único que se enseña."""
    name: str
    currency: str


@dataclass(frozen=True, slots=True)
class BankLink:
    """Una cuenta del banco y la cuenta del hogar a la que alimenta (si ya se eligió)."""

    remote_uid: str
    iban_tail: str
    name: str
    currency: str
    account_id: AccountId | None = None
    bank_balance: Money | None = None
    """Último saldo que informó el banco."""
    bank_balance_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RemoteBalance:
    amount: Money
    at: datetime


@dataclass(frozen=True, slots=True)
class RemoteTransaction:
    """Un movimiento contabilizado tal como lo da el agregador, ya con el signo de la cuenta."""

    entry_id: str | None
    booked_on: date
    amount: Decimal
    currency: str
    description: str


@dataclass(frozen=True, slots=True)
class BankConnection:
    id: UUID
    household_id: WorkspaceId
    owner_id: UserId
    aspsp: str
    country: str
    status: ConsentStatus
    created_at: datetime
    state: str = ""
    """Valor de un solo uso que une la vuelta del banco con esta conexión; vacío al activarla."""
    session_id: str | None = None
    """Sesión del agregador. Es una credencial: no sale por la API ni por los logs."""
    valid_until: datetime | None = None
    last_sync_at: datetime | None = None
    last_error: str = ""
    links: tuple[BankLink, ...] = field(default_factory=tuple)

    def activate(
        self, session_id: str, accounts: Iterable[BankAccountRef], valid_until: datetime
    ) -> BankConnection:
        if self.status is not ConsentStatus.PENDING:
            raise BankError("Esta conexión ya no espera autorización")
        links = tuple(BankLink(a.uid, a.iban_tail, a.name, a.currency) for a in accounts)
        return replace(
            self,
            status=ConsentStatus.ACTIVE,
            state="",
            session_id=session_id,
            valid_until=valid_until,
            links=links,
        )

    def is_expired(self, now: datetime) -> bool:
        return (
            self.status is ConsentStatus.ACTIVE
            and self.valid_until is not None
            and self.valid_until <= now
        )

    def current(self, now: datetime) -> BankConnection:
        """La conexión con su estado al día: una activa cuyo plazo pasó es caducada."""
        return replace(self, status=ConsentStatus.EXPIRED) if self.is_expired(now) else self

    def expires_soon(self, now: datetime) -> bool:
        return (
            self.status is ConsentStatus.ACTIVE
            and self.valid_until is not None
            and now < self.valid_until <= now + timedelta(days=EXPIRY_WARNING_DAYS)
        )

    def link_to(self, remote_uid: str, account_id: AccountId | None) -> BankConnection:
        """Enlaza (o desenlaza, con ``None``) una cuenta del banco con una del hogar."""
        if self.status is not ConsentStatus.ACTIVE:
            raise BankError("Solo se enlazan cuentas de una conexión activa")
        if account_id is not None and any(
            link.account_id == account_id and link.remote_uid != remote_uid for link in self.links
        ):
            raise BankError("Esa cuenta ya recibe movimientos de otra cuenta del banco")
        if not any(link.remote_uid == remote_uid for link in self.links):
            raise BankError("Cuenta del banco no encontrada")
        return replace(
            self,
            links=tuple(
                replace(link, account_id=account_id) if link.remote_uid == remote_uid else link
                for link in self.links
            ),
        )

    def with_balance(self, remote_uid: str, balance: RemoteBalance) -> BankConnection:
        return replace(
            self,
            links=tuple(
                replace(link, bank_balance=balance.amount, bank_balance_at=balance.at)
                if link.remote_uid == remote_uid
                else link
                for link in self.links
            ),
        )

    def synced(self, at: datetime) -> BankConnection:
        return replace(self, last_sync_at=at, last_error="")

    def failed(self, reason: str) -> BankConnection:
        return replace(self, last_error=reason[:MAX_ERROR])

    def revoked(self) -> BankConnection:
        return replace(self, status=ConsentStatus.REVOKED, state="", session_id=None)

    def sync_start(self, now: datetime) -> date:
        """Desde qué día pedir movimientos."""
        if self.last_sync_at is None:
            return (now - timedelta(days=FIRST_SYNC_DAYS)).date()
        return (self.last_sync_at - timedelta(days=OVERLAP_DAYS)).date()


def bank_fingerprint(connection_id: UUID, remote_uid: str, tx: RemoteTransaction) -> str | None:
    """Huella de un movimiento con identificador del banco; ``None`` si el banco no lo da."""
    if not tx.entry_id:
        return None
    payload = f"bank|{connection_id}|{remote_uid}|{tx.entry_id}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _fallback_fingerprint(
    connection_id: UUID, remote_uid: str, tx: RemoteTransaction, occurrence: int
) -> str:
    payload = "|".join(
        [
            "bank-noid",
            str(connection_id),
            remote_uid,
            tx.booked_on.isoformat(),
            str(tx.amount),
            tx.currency,
            re.sub(r"\s+", " ", tx.description).strip().casefold(),
            str(occurrence),
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def to_rows(
    connection_id: UUID,
    remote_uid: str,
    transactions: Iterable[RemoteTransaction],
    rules: ClassificationRules,
    currency: Currency,
) -> tuple[list[ImportedRow], int]:
    """Convierte lo del banco en filas de extracto, de la más antigua a la más reciente.

    Devuelve las filas y cuántos movimientos se descartan por moneda distinta o importe cero.
    Los movimientos sin identificador se distinguen por su orden dentro del mismo día, importe
    y concepto, igual que dos cafés iguales en un extracto.
    """
    rows: list[ImportedRow] = []
    skipped = 0
    seen: dict[tuple[date, Decimal, str, str], int] = {}
    ordered = sorted(transactions, key=lambda t: (t.booked_on, t.entry_id or ""))
    for index, tx in enumerate(ordered, start=1):
        if tx.currency != currency.code or tx.amount == 0:
            skipped += 1
            continue
        description = re.sub(r"\s+", " ", tx.description).strip() or "Movimiento bancario"
        fp = bank_fingerprint(connection_id, remote_uid, tx)
        if fp is None:
            key = (tx.booked_on, tx.amount, tx.currency, description.casefold())
            occurrence = seen.get(key, 0)
            seen[key] = occurrence + 1
            fp = _fallback_fingerprint(connection_id, remote_uid, tx, occurrence)
        amount = Money(tx.amount, currency)
        kind, member = suggest_kind(description, tx.amount > 0, rules)
        rows.append(
            ImportedRow(
                booked_at=datetime.combine(tx.booked_on, time.min),
                value_date=tx.booked_on,
                description=description[:500],
                amount=amount,
                bank_type="PSD2",
                suggested_kind=kind,
                fingerprint=fp,
                member=member,
                line=index,
            )
        )
    return rows, skipped


def reconcile_candidate(
    row: ImportedRow, existing: Iterable[Transaction], taken: set[UUID]
) -> Transaction | None:
    """El movimiento ya anotado que corresponde a una fila del banco, si es uno solo.

    Mismo importe y fecha a ``RECONCILE_DAYS`` como mucho, de la misma cuenta, que no venga
    ya del banco ni se haya usado en esta pasada. Con varios candidatos no se adivina.
    """
    matches = [
        t
        for t in existing
        if not t.voided
        and t.id not in taken
        and not t.source.startswith(SOURCE_PREFIX)
        and t.amount == row.amount
        and abs((t.booked_at.date() - row.booked_at.date()).days) <= RECONCILE_DAYS
    ]
    return matches[0] if len(matches) == 1 else None
