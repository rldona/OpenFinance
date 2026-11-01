from __future__ import annotations

import calendar
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from openfinance.application.errors import ConflictError
from openfinance.application.ports import StoredSession, TransactionQuery
from openfinance.domain.categories import Category, CategoryId, CategoryRule
from openfinance.domain.identity import User
from openfinance.domain.imports.batch import PREVIEW_TTL, ImportBatch, ImportStatus
from openfinance.domain.insights import Month
from openfinance.domain.ledger import (
    Account,
    AccountKind,
    Institution,
    Transaction,
    TransactionKind,
)
from openfinance.domain.savings import Budget, Goal, GoalId
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
    BudgetRow,
    CategoryRow,
    CategoryRuleRow,
    GoalRow,
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
        category_id=CategoryId(row.category_id) if row.category_id else None,
        merchant=row.merchant,
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
        if query.category_id is not None:
            stmt = stmt.where(TransactionRow.category_id == query.category_id)
        if query.uncategorized:
            stmt = stmt.where(
                TransactionRow.kind == TransactionKind.EXPENSE.value,
                TransactionRow.category_id.is_(None),
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
                category_id=t.category_id,
                merchant=t.merchant,
                member_id=t.member_id,
                bank_type=t.bank_type,
                source=t.source,
                fingerprint=t.fingerprint,
                import_id=t.import_id,
            )
        )
        _flush(self._s)

    def get(self, household_id: WorkspaceId, transaction_id: TransactionId) -> Transaction | None:
        row = self._s.scalar(
            select(TransactionRow).where(
                TransactionRow.id == transaction_id, TransactionRow.household_id == household_id
            )
        )
        return _transaction(row) if row else None

    def set_category(
        self, household_id: WorkspaceId, ids: list[TransactionId], category_id: CategoryId | None
    ) -> None:
        for i in range(0, len(ids), 500):
            self._s.execute(
                update(TransactionRow)
                .where(
                    TransactionRow.household_id == household_id,
                    TransactionRow.id.in_(ids[i : i + 500]),
                    TransactionRow.kind == TransactionKind.EXPENSE.value,
                )
                .values(category_id=category_id)
            )
        _flush(self._s)

    def _uncategorized(self, household_id: WorkspaceId, account_ids: list[AccountId]):  # type: ignore[no-untyped-def]
        return (
            TransactionRow.household_id == household_id,
            TransactionRow.account_id.in_(account_ids),
            TransactionRow.kind == TransactionKind.EXPENSE.value,
            TransactionRow.category_id.is_(None),
        )

    def uncategorized_with_merchant_word(
        self, household_id: WorkspaceId, account_ids: list[AccountId], first_word: str
    ) -> list[Transaction]:
        rows = self._s.scalars(
            select(TransactionRow).where(
                *self._uncategorized(household_id, account_ids),
                or_(
                    TransactionRow.merchant == first_word,
                    TransactionRow.merchant.startswith(f"{first_word} ", autoescape=True),
                ),
            )
        )
        return [_transaction(r) for r in rows]

    def in_range(
        self,
        household_id: WorkspaceId,
        account_ids: list[AccountId],
        start: datetime,
        end: datetime,
        *,
        only_category: bool = False,
        category_id: CategoryId | None = None,
    ) -> list[Transaction]:
        if not account_ids:
            return []
        stmt = select(TransactionRow).where(
            TransactionRow.household_id == household_id,
            TransactionRow.account_id.in_(account_ids),
            TransactionRow.booked_at.between(start, end),
        )
        if only_category:
            stmt = stmt.where(
                TransactionRow.category_id.is_(None)
                if category_id is None
                else TransactionRow.category_id == category_id
            )
        return [_transaction(r) for r in self._s.scalars(stmt.order_by(TransactionRow.booked_at))]

    def first_booked_at(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> datetime | None:
        if not account_ids:
            return None
        return self._s.scalar(
            select(func.min(TransactionRow.booked_at)).where(
                TransactionRow.household_id == household_id,
                TransactionRow.account_id.in_(account_ids),
            )
        )

    def count_uncategorized(self, household_id: WorkspaceId, account_ids: list[AccountId]) -> int:
        return int(
            self._s.scalar(
                select(func.count())
                .select_from(TransactionRow)
                .where(*self._uncategorized(household_id, account_ids))
            )
            or 0
        )

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


def _category(row: CategoryRow) -> Category:
    return Category(
        id=CategoryId(row.id),
        household_id=WorkspaceId(row.household_id),
        name=row.name,
        icon=row.icon,
        color=row.color,
        hidden=row.hidden,
        slug=row.slug,
        position=row.position,
    )


class SqlCategoryRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[Category]:
        rows = self._s.scalars(
            select(CategoryRow)
            .where(CategoryRow.household_id == household_id)
            .order_by(CategoryRow.position, CategoryRow.name)
        )
        return [_category(r) for r in rows]

    def get(self, household_id: WorkspaceId, category_id: CategoryId) -> Category | None:
        row = self._s.scalar(
            select(CategoryRow).where(
                CategoryRow.id == category_id, CategoryRow.household_id == household_id
            )
        )
        return _category(row) if row else None

    def add(self, category: Category) -> None:
        self._s.add(
            CategoryRow(
                id=category.id,
                household_id=category.household_id,
                name=category.name,
                key=category.key[:50],
                icon=category.icon,
                color=category.color,
                hidden=category.hidden,
                slug=category.slug,
                position=category.position,
            )
        )
        _flush(self._s)

    def update(self, category: Category) -> None:
        row = self._s.get(CategoryRow, category.id)
        if row is None or row.household_id != category.household_id:
            raise LookupError(category.id)
        row.name = category.name
        row.key = category.key[:50]
        row.icon = category.icon
        row.color = category.color
        row.hidden = category.hidden
        _flush(self._s)


class SqlRuleRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[CategoryRule]:
        rows = self._s.scalars(
            select(CategoryRuleRow).where(CategoryRuleRow.household_id == household_id)
        )
        return [
            CategoryRule(
                WorkspaceId(r.household_id), r.merchant, CategoryId(r.category_id), r.scope
            )
            for r in rows
        ]

    def upsert(self, rule: CategoryRule, now: datetime) -> None:
        row = self._s.get(CategoryRuleRow, (rule.household_id, rule.scope, rule.merchant))
        if row is None:
            self._s.add(
                CategoryRuleRow(
                    household_id=rule.household_id,
                    scope=rule.scope,
                    merchant=rule.merchant,
                    category_id=rule.category_id,
                    updated_at=now,
                )
            )
        else:
            row.category_id = rule.category_id
            row.updated_at = now
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, scope: str, merchant: str) -> None:
        self._s.execute(
            delete(CategoryRuleRow).where(
                CategoryRuleRow.household_id == household_id,
                CategoryRuleRow.scope == scope,
                CategoryRuleRow.merchant == merchant,
            )
        )


class SqlBudgetRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[Budget]:
        rows = self._s.scalars(select(BudgetRow).where(BudgetRow.household_id == household_id))
        return [
            Budget(
                WorkspaceId(r.household_id),
                CategoryId(r.category_id),
                Money.of(r.amount, r.currency),
            )
            for r in rows
        ]

    def upsert(self, budget: Budget) -> None:
        row = self._s.get(BudgetRow, (budget.household_id, budget.category_id))
        if row is None:
            self._s.add(
                BudgetRow(
                    household_id=budget.household_id,
                    category_id=budget.category_id,
                    amount=budget.amount.amount,
                    currency=budget.amount.currency.code,
                )
            )
        else:
            row.amount = budget.amount.amount
            row.currency = budget.amount.currency.code
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, category_id: CategoryId) -> None:
        self._s.execute(
            delete(BudgetRow).where(
                BudgetRow.household_id == household_id, BudgetRow.category_id == category_id
            )
        )


def _goal(row: GoalRow) -> Goal:
    return Goal(
        id=GoalId(row.id),
        household_id=WorkspaceId(row.household_id),
        name=row.name,
        icon=row.icon,
        target=Money.of(row.target, row.currency),
        monthly=Money.of(row.monthly, row.currency),
        saved=Money.of(row.saved, row.currency),
        deadline=Month.parse(row.deadline) if row.deadline else None,
        account_id=AccountId(row.account_id) if row.account_id else None,
    )


def _goal_values(goal: Goal) -> dict[str, object]:
    return {
        "name": goal.name,
        "icon": goal.icon,
        "target": goal.target.amount,
        "monthly": goal.monthly.amount,
        "saved": goal.saved.amount,
        "currency": goal.target.currency.code,
        "deadline": str(goal.deadline) if goal.deadline else None,
        "account_id": goal.account_id,
    }


class SqlGoalRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[Goal]:
        rows = self._s.scalars(
            select(GoalRow)
            .where(GoalRow.household_id == household_id)
            .order_by(GoalRow.created_at, GoalRow.name)
        )
        return [_goal(r) for r in rows]

    def get(self, household_id: WorkspaceId, goal_id: GoalId) -> Goal | None:
        row = self._s.scalar(
            select(GoalRow).where(GoalRow.id == goal_id, GoalRow.household_id == household_id)
        )
        return _goal(row) if row else None

    def add(self, goal: Goal) -> None:
        self._s.add(GoalRow(id=goal.id, household_id=goal.household_id, **_goal_values(goal)))
        _flush(self._s)

    def update(self, goal: Goal) -> None:
        self._s.execute(
            update(GoalRow)
            .where(GoalRow.id == goal.id, GoalRow.household_id == goal.household_id)
            .values(**_goal_values(goal))
        )
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, goal_id: GoalId) -> None:
        self._s.execute(
            delete(GoalRow).where(GoalRow.id == goal_id, GoalRow.household_id == household_id)
        )


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
        self.categories = SqlCategoryRepository(session)
        self.rules = SqlRuleRepository(session)
        self.budgets = SqlBudgetRepository(session)
        self.goals = SqlGoalRepository(session)

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "Los datos han cambiado mientras guardabas; vuelve a intentarlo"
            ) from exc
