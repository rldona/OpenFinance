"""Repositorio de conexiones con el banco (ADR-0024)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.bank import BankConnection, BankLink, ConsentStatus
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, UserId, WorkspaceId
from openfinance.infrastructure.db.models import BankConnectionRow, BankLinkRow
from openfinance.infrastructure.db.repositories._common import _as_utc, _flush


def _opt(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value else None


def _link(row: BankLinkRow) -> BankLink:
    balance = (
        Money(row.bank_balance, Currency(row.currency)) if row.bank_balance is not None else None
    )
    return BankLink(
        row.remote_uid,
        row.iban_tail,
        row.name,
        row.currency,
        AccountId(row.account_id) if row.account_id else None,
        balance,
        _opt(row.bank_balance_at),
    )


class SqlBankRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def _domain(self, row: BankConnectionRow) -> BankConnection:
        links = self._s.scalars(
            select(BankLinkRow)
            .where(BankLinkRow.connection_id == row.id)
            .order_by(BankLinkRow.name, BankLinkRow.remote_uid)
        )
        return BankConnection(
            id=row.id,
            household_id=WorkspaceId(row.household_id),
            owner_id=UserId(row.owner_id),
            aspsp=row.aspsp,
            country=row.country,
            status=ConsentStatus(row.status),
            created_at=_as_utc(row.created_at),
            state=row.state,
            session_id=row.session_id,
            valid_until=_opt(row.valid_until),
            last_sync_at=_opt(row.last_sync_at),
            last_error=row.last_error,
            links=tuple(_link(link) for link in links),
        )

    def add(self, connection: BankConnection) -> None:
        self._s.add(
            BankConnectionRow(
                id=connection.id,
                household_id=connection.household_id,
                owner_id=connection.owner_id,
                aspsp=connection.aspsp,
                country=connection.country,
                created_at=connection.created_at,
                status=connection.status.value,
            )
        )
        _flush(self._s)
        self.save(connection)

    def save(self, connection: BankConnection) -> None:
        row = self._s.get(BankConnectionRow, connection.id)
        if row is None:
            raise LookupError("Conexión inexistente")
        row.status = connection.status.value
        row.state = connection.state
        row.session_id = connection.session_id
        row.valid_until = connection.valid_until
        row.last_sync_at = connection.last_sync_at
        row.last_error = connection.last_error
        self._s.execute(delete(BankLinkRow).where(BankLinkRow.connection_id == connection.id))
        _flush(self._s)
        for link in connection.links:
            self._s.add(
                BankLinkRow(
                    connection_id=connection.id,
                    remote_uid=link.remote_uid,
                    iban_tail=link.iban_tail,
                    name=link.name,
                    currency=link.currency,
                    account_id=link.account_id,
                    bank_balance=link.bank_balance.amount if link.bank_balance else None,
                    bank_balance_at=link.bank_balance_at,
                )
            )
        _flush(self._s)

    def get(self, household_id: WorkspaceId, connection_id: UUID) -> BankConnection | None:
        row = self._s.scalar(
            select(BankConnectionRow).where(
                BankConnectionRow.household_id == household_id,
                BankConnectionRow.id == connection_id,
            )
        )
        return self._domain(row) if row else None

    def by_state(self, state: str) -> BankConnection | None:
        if not state:
            return None
        row = self._s.scalar(
            select(BankConnectionRow).where(
                BankConnectionRow.state == state,
                BankConnectionRow.status == ConsentStatus.PENDING.value,
            )
        )
        return self._domain(row) if row else None

    def for_owner(self, household_id: WorkspaceId, owner_id: UserId) -> list[BankConnection]:
        rows = self._s.scalars(
            select(BankConnectionRow)
            .where(
                BankConnectionRow.household_id == household_id,
                BankConnectionRow.owner_id == owner_id,
            )
            .order_by(BankConnectionRow.created_at.desc(), BankConnectionRow.id)
        )
        return [self._domain(r) for r in rows]

    def active(self) -> list[BankConnection]:
        rows = self._s.scalars(
            select(BankConnectionRow)
            .where(BankConnectionRow.status == ConsentStatus.ACTIVE.value)
            .order_by(BankConnectionRow.created_at, BankConnectionRow.id)
        )
        return [self._domain(r) for r in rows]

    def linked_to(self, household_id: WorkspaceId, account_id: AccountId) -> bool:
        return (
            self._s.scalar(
                select(BankLinkRow.connection_id)
                .join(BankConnectionRow, BankConnectionRow.id == BankLinkRow.connection_id)
                .where(
                    BankConnectionRow.household_id == household_id,
                    BankConnectionRow.status == ConsentStatus.ACTIVE.value,
                    BankLinkRow.account_id == account_id,
                )
                .limit(1)
            )
            is not None
        )
