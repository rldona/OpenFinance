from __future__ import annotations

import calendar
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.application.ports import StoredSession, TransactionQuery
from openfinance.domain.identity import User
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
    MembershipRow,
    SessionRow,
    TransactionRow,
    UserRow,
)


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
            )
        )
        self._s.flush()


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


class SqlUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = SqlUserRepository(session)
        self.households = SqlHouseholdRepository(session)
        self.accounts = SqlAccountRepository(session)
        self.transactions = SqlTransactionRepository(session)
        self.sessions = SqlSessionRepository(session)

    def commit(self) -> None:
        self.session.commit()
