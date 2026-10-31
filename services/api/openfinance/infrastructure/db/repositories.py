from __future__ import annotations

import calendar
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from openfinance.application.errors import ConflictError
from openfinance.application.ports import StoredSession, TransactionQuery
from openfinance.domain.identity import User
from openfinance.domain.imports.batch import PREVIEW_TTL, ImportBatch, ImportStatus
from openfinance.domain.ledger import (
    Account,
    AccountKind,
    Institution,
    Transaction,
    TransactionKind,
)
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import (
    AccountId,
    TransactionId,
    UserId,
    WorkspaceId,
)
from openfinance.domain.workspaces import Household
from openfinance.infrastructure.db.models import (
    AccountRow,
    HouseholdRow,
    ImportBatchRow,
    MembershipRow,
    SessionRow,
    TransactionRow,
    UserRow,
)

_CONFLICT = "Los datos han cambiado mientras guardabas; vuelve a intentarlo"


def _flush(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            "Los datos han cambiado mientras guardabas; vuelve a intentarlo"
        ) from exc


def _as_utc(value: datetime) -> datetime:
    """SQLite devuelve fechas sin zona; las guardamos siempre en UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _user(row: UserRow) -> User:
    return User(UserId(row.id), row.email, row.display_name, row.password_hash)


class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, user_id: UserId) -> User | None:
        row = self._s.get(UserRow, user_id)
        return _user(row) if row else None

    def get_by_email(self, email: str) -> User | None:
        row = self._s.scalar(select(UserRow).where(UserRow.email == email))
        return _user(row) if row else None

    def add(self, user: User) -> None:
        self._s.add(
            UserRow(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                password_hash=user.password_hash,
            )
        )
        self._s.flush()


class SqlHouseholdRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, household_id: WorkspaceId) -> Household | None:
        row = self._s.get(HouseholdRow, household_id)
        return Household(WorkspaceId(row.id), row.name, Currency(row.currency)) if row else None

    def add(self, household: Household) -> None:
        self._s.add(
            HouseholdRow(id=household.id, name=household.name, currency=household.currency.code)
        )
        self._s.flush()

    def add_member(self, household_id: WorkspaceId, user_id: UserId) -> None:
        self._s.add(MembershipRow(household_id=household_id, user_id=user_id))
        self._s.flush()

    def households_of(self, user_id: UserId) -> list[WorkspaceId]:
        rows = self._s.scalars(
            select(MembershipRow.household_id)
            .where(MembershipRow.user_id == user_id)
            .order_by(MembershipRow.created_at)
        )
        return [WorkspaceId(h) for h in rows]

    def members(self, household_id: WorkspaceId) -> list[User]:
        rows = self._s.scalars(
            select(UserRow)
            .join(MembershipRow, MembershipRow.user_id == UserRow.id)
            .where(MembershipRow.household_id == household_id)
            .order_by(UserRow.display_name)
        )
        return [_user(r) for r in rows]


_KIND_ORDER = {AccountKind.JOINT: 0, AccountKind.SAVINGS: 1, AccountKind.PERSONAL: 2}


def _account(row: AccountRow) -> Account:
    currency = Currency(row.currency)
    return Account(
        id=AccountId(row.id),
        household_id=WorkspaceId(row.household_id),
        name=row.name,
        institution=Institution(row.institution),
        kind=AccountKind(row.kind),
        currency=currency,
        opening_balance=Money.of(row.opening_balance, currency),
        owner_id=UserId(row.owner_id) if row.owner_id else None,
    )


class SqlAccountRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[Account]:
        rows = self._s.scalars(select(AccountRow).where(AccountRow.household_id == household_id))
        return sorted((_account(r) for r in rows), key=lambda a: (_KIND_ORDER[a.kind], a.name))

    def add(self, account: Account) -> None:
        self._s.add(
            AccountRow(
                id=account.id,
                household_id=account.household_id,
                name=account.name,
                institution=account.institution.value,
                kind=account.kind.value,
                currency=account.currency.code,
                opening_balance=account.opening_balance.amount,
                owner_id=account.owner_id,
            )
        )
        self._s.flush()


def _transaction(row: TransactionRow) -> Transaction:
    return Transaction(
        id=TransactionId(row.id),
        household_id=WorkspaceId(row.household_id),
        account_id=AccountId(row.account_id),
        booked_at=row.booked_at,
        value_date=row.value_date,
        description=row.description,
        amount=Money.of(row.amount, row.currency),
        kind=TransactionKind(row.kind),
        category=row.category,
        member_id=UserId(row.member_id) if row.member_id else None,
        bank_type=row.bank_type,
        source=row.source,
        fingerprint=row.fingerprint,
        import_id=row.import_id,
    )


class SqlTransactionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def search(
        self, household_id: WorkspaceId, account_ids: list[AccountId], query: TransactionQuery
    ) -> list[Transaction]:
        stmt = select(TransactionRow).where(
            TransactionRow.household_id == household_id,
            TransactionRow.account_id.in_(account_ids),
        )
        if query.year is not None and query.month is not None:
            last_day = calendar.monthrange(query.year, query.month)[1]
            start = datetime(query.year, query.month, 1)  # noqa: DTZ001 - hora local del banco
            end = datetime(query.year, query.month, last_day, 23, 59, 59, 999999)  # noqa: DTZ001
            stmt = stmt.where(TransactionRow.booked_at.between(start, end))
        if query.text:
            stmt = stmt.where(
                TransactionRow.description.icontains(query.text.strip(), autoescape=True)
            )
        if query.uncategorized:
            stmt = stmt.where(
                TransactionRow.kind == TransactionKind.EXPENSE.value,
                TransactionRow.category.is_(None),
            )
        stmt = stmt.order_by(TransactionRow.booked_at.desc(), TransactionRow.id).limit(query.limit)
        return [_transaction(r) for r in self._s.scalars(stmt)]

    def for_account(self, household_id: WorkspaceId, account_id: AccountId) -> list[Transaction]:
        rows = self._s.scalars(
            select(TransactionRow).where(
                TransactionRow.household_id == household_id,
                TransactionRow.account_id == account_id,
            )
        )
        return [_transaction(r) for r in rows]

    def add(self, transaction: Transaction) -> None:
        t = transaction
        self._s.add(
            TransactionRow(
                id=t.id,
                household_id=t.household_id,
                account_id=t.account_id,
                booked_at=t.booked_at,
                value_date=t.value_date,
                description=t.description,
                amount=t.amount.amount,
                currency=t.amount.currency.code,
                kind=t.kind.value,
                category=t.category,
                member_id=t.member_id,
                bank_type=t.bank_type,
                source=t.source,
                fingerprint=t.fingerprint,
                import_id=t.import_id,
            )
        )
        _flush(self._s)

    def existing_fingerprints(
        self, household_id: WorkspaceId, account_id: AccountId, fingerprints: list[str]
    ) -> set[str]:
        found: set[str] = set()
        for i in range(0, len(fingerprints), 500):
            chunk = fingerprints[i : i + 500]
            found.update(
                f
                for f in self._s.scalars(
                    select(TransactionRow.fingerprint).where(
                        TransactionRow.household_id == household_id,
                        TransactionRow.account_id == account_id,
                        TransactionRow.fingerprint.in_(chunk),
                    )
                )
                if f is not None
            )
        return found


class SqlSessionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, session: StoredSession) -> None:
        self._s.add(
            SessionRow(
                token_hash=session.token_hash,
                user_id=session.user_id,
                household_id=session.household_id,
                expires_at=session.expires_at,
            )
        )
        self._s.flush()

    def get(self, token_hash: str) -> StoredSession | None:
        row = self._s.get(SessionRow, token_hash)
        if row is None:
            return None
        return StoredSession(
            row.token_hash,
            UserId(row.user_id),
            WorkspaceId(row.household_id),
            _as_utc(row.expires_at),
        )

    def delete(self, token_hash: str) -> None:
        self._s.execute(delete(SessionRow).where(SessionRow.token_hash == token_hash))

    def delete_expired(self, now: datetime) -> int:
        result = self._s.execute(delete(SessionRow).where(SessionRow.expires_at <= now))
        return int(getattr(result, "rowcount", 0) or 0)


def _batch(row: ImportBatchRow) -> ImportBatch:
    return ImportBatch(
        id=row.id,
        household_id=WorkspaceId(row.household_id),
        account_id=AccountId(row.account_id),
        filename=row.filename,
        created_by=UserId(row.created_by),
        created_at=_as_utc(row.created_at),
        status=ImportStatus(row.status),
        committed_at=_as_utc(row.committed_at) if row.committed_at else None,
        created_count=row.created_count,
        duplicate_count=row.duplicate_count,
        skipped_count=row.skipped_count,
    )


class SqlImportBatchRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, batch: ImportBatch, content: bytes) -> None:
        self._s.add(
            ImportBatchRow(
                id=batch.id,
                household_id=batch.household_id,
                account_id=batch.account_id,
                filename=batch.filename,
                content=content,
                status=batch.status.value,
                created_by=batch.created_by,
                created_at=batch.created_at,
            )
        )
        self._s.flush()

    def get(self, household_id: WorkspaceId, batch_id: UUID) -> ImportBatch | None:
        row = self._s.scalar(
            select(ImportBatchRow).where(
                ImportBatchRow.id == batch_id, ImportBatchRow.household_id == household_id
            )
        )
        return _batch(row) if row else None

    def content(self, batch_id: UUID) -> bytes | None:
        return self._s.scalar(select(ImportBatchRow.content).where(ImportBatchRow.id == batch_id))

    def claim(self, batch_id: UUID) -> bool:
        result = self._s.execute(
            update(ImportBatchRow)
            .where(
                ImportBatchRow.id == batch_id,
                ImportBatchRow.status == ImportStatus.PREVIEW.value,
            )
            .values(status=ImportStatus.COMMITTED.value)
        )
        return bool(getattr(result, "rowcount", 0))

    def purge_expired_content(self, now: datetime) -> None:
        self._s.execute(
            update(ImportBatchRow)
            .where(
                ImportBatchRow.status == ImportStatus.PREVIEW.value,
                ImportBatchRow.created_at < now - PREVIEW_TTL,
                ImportBatchRow.content.is_not(None),
            )
            .values(content=None)
        )

    def save_committed(self, batch: ImportBatch) -> None:
        row = self._s.get(ImportBatchRow, batch.id)
        if row is None:
            raise LookupError(batch.id)
        row.status = batch.status.value
        row.committed_at = batch.committed_at
        row.created_count = batch.created_count
        row.duplicate_count = batch.duplicate_count
        row.skipped_count = batch.skipped_count
        row.content = None
        self._s.flush()


class SqlUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = SqlUserRepository(session)
        self.households = SqlHouseholdRepository(session)
        self.accounts = SqlAccountRepository(session)
        self.transactions = SqlTransactionRepository(session)
        self.sessions = SqlSessionRepository(session)
        self.imports = SqlImportBatchRepository(session)

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "Los datos han cambiado mientras guardabas; vuelve a intentarlo"
            ) from exc
