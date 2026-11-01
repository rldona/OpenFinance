from __future__ import annotations

import calendar
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from openfinance.application.errors import ConflictError
from openfinance.application.ports import StoredSession, TransactionQuery
from openfinance.domain.categories import Category, CategoryId, CategoryRule
from openfinance.domain.changes import Change, Entity, Operation
from openfinance.domain.identity import User
from openfinance.domain.imports import MemberPattern, PatternDirection
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
    ChangeEntryRow,
    ChangeOperationRow,
    DismissedIdeaRow,
    GoalRow,
    HouseholdRow,
    ImportBatchRow,
    MemberPatternRow,
    MembershipRow,
    SessionRow,
    TransactionRow,
    UserRow,
)

_AMOUNT_QUANTUM = Decimal("0.0001")
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

    def set_password_hash(self, user_id: UserId, password_hash: str) -> None:
        self._s.execute(
            update(UserRow).where(UserRow.id == user_id).values(password_hash=password_hash)
        )


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
        note=row.note,
        voided=row.voided,
    )


_ACTIVE = TransactionRow.voided.is_(False)
"""Los movimientos anulados no cuentan en ninguna consulta (ADR-0017)."""


def _new_row(t: Transaction) -> TransactionRow:
    return TransactionRow(
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
        note=t.note,
        voided=t.voided,
    )


class SqlTransactionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def _filtered(
        self, household_id: WorkspaceId, account_ids: list[AccountId], query: TransactionQuery
    ) -> Select[TransactionRow]:
        stmt = select(TransactionRow).where(
            TransactionRow.household_id == household_id,
            TransactionRow.account_id.in_(account_ids),
            _ACTIVE,
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
        return stmt

    def search(
        self, household_id: WorkspaceId, account_ids: list[AccountId], query: TransactionQuery
    ) -> list[Transaction]:
        stmt = self._filtered(household_id, account_ids, query)
        if query.after is not None:
            # Orden del listado: fecha descendente y, a igual fecha, identificador ascendente.
            at, last_id = query.after
            stmt = stmt.where(
                or_(
                    TransactionRow.booked_at < at,
                    and_(TransactionRow.booked_at == at, TransactionRow.id > last_id),
                )
            )
        stmt = stmt.order_by(TransactionRow.booked_at.desc(), TransactionRow.id).limit(query.limit)
        return [_transaction(r) for r in self._s.scalars(stmt)]

    def totals(
        self, household_id: WorkspaceId, account_ids: list[AccountId], query: TransactionQuery
    ) -> tuple[int, Decimal]:
        filtered = self._filtered(household_id, account_ids, query).subquery()
        count = 0
        total = Decimal(0)
        # Se suma en Python: SUM sobre decimales exactos no es fiable en todos los motores.
        for (amount,) in self._s.execute(select(filtered.c.amount)):
            count += 1
            total += amount
        return count, total

    def for_account(self, household_id: WorkspaceId, account_id: AccountId) -> list[Transaction]:
        rows = self._s.scalars(
            select(TransactionRow).where(
                TransactionRow.household_id == household_id,
                TransactionRow.account_id == account_id,
                _ACTIVE,
            )
        )
        return [_transaction(r) for r in rows]

    def balances(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> dict[AccountId, Decimal]:
        """Lo que suman los movimientos activos de cada cuenta, calculado en la base de datos
        (OF-905): sin cargar los movimientos. Una cuenta sin movimientos no aparece."""
        if not account_ids:
            return {}
        rows = self._s.execute(
            select(TransactionRow.account_id, func.sum(TransactionRow.amount))
            .where(
                TransactionRow.household_id == household_id,
                TransactionRow.account_id.in_(account_ids),
                _ACTIVE,
            )
            .group_by(TransactionRow.account_id)
        )
        # SQLite suma en coma flotante: se redondea a la escala de la columna (4 decimales).
        return {
            AccountId(account_id): Decimal(str(total or 0)).quantize(_AMOUNT_QUANTUM)
            for account_id, total in rows
        }

    def add(self, transaction: Transaction) -> None:
        self.add_many([transaction])

    def add_many(self, transactions: list[Transaction]) -> None:
        """Inserta varios movimientos con un solo flush (OF-905)."""
        if not transactions:
            return
        self._s.add_all([_new_row(t) for t in transactions])
        _flush(self._s)

    def get(
        self,
        household_id: WorkspaceId,
        transaction_id: TransactionId,
        *,
        include_voided: bool = False,
    ) -> Transaction | None:
        stmt = select(TransactionRow).where(
            TransactionRow.id == transaction_id, TransactionRow.household_id == household_id
        )
        if not include_voided:
            stmt = stmt.where(_ACTIVE)
        row = self._s.scalar(stmt)
        return _transaction(row) if row else None

    def save(self, transaction: Transaction) -> None:
        """Guarda los campos corregibles (ADR-0017); el resto del movimiento no cambia."""
        t = transaction
        self._s.execute(
            update(TransactionRow)
            .where(TransactionRow.id == t.id, TransactionRow.household_id == t.household_id)
            .values(
                kind=t.kind.value,
                member_id=t.member_id,
                category_id=t.category_id,
                note=t.note,
                voided=t.voided,
                import_id=t.import_id,
            )
        )
        _flush(self._s)

    def for_import(self, household_id: WorkspaceId, import_id: UUID) -> list[Transaction]:
        rows = self._s.scalars(
            select(TransactionRow)
            .where(
                TransactionRow.household_id == household_id,
                TransactionRow.import_id == import_id,
                _ACTIVE,
            )
            .order_by(TransactionRow.booked_at)
        )
        return [_transaction(r) for r in rows]

    def accounts_of(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, AccountId]:
        out: dict[TransactionId, AccountId] = {}
        for i in range(0, len(ids), 500):
            rows = self._s.execute(
                select(TransactionRow.id, TransactionRow.account_id).where(
                    TransactionRow.household_id == household_id,
                    TransactionRow.id.in_(ids[i : i + 500]),
                )
            )
            out.update({TransactionId(r.id): AccountId(r.account_id) for r in rows})
        return out

    def voided_with_fingerprints(
        self, household_id: WorkspaceId, account_id: AccountId, fingerprints: list[str]
    ) -> dict[str, Transaction]:
        """Movimientos anulados con esas huellas: se reactivan al volver a importar."""
        found: dict[str, Transaction] = {}
        for i in range(0, len(fingerprints), 500):
            rows = self._s.scalars(
                select(TransactionRow).where(
                    TransactionRow.household_id == household_id,
                    TransactionRow.account_id == account_id,
                    TransactionRow.fingerprint.in_(fingerprints[i : i + 500]),
                    TransactionRow.voided.is_(True),
                )
            )
            found.update({r.fingerprint: _transaction(r) for r in rows if r.fingerprint})
        return found

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
                    _ACTIVE,
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
            _ACTIVE,
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
            _ACTIVE,
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
                _ACTIVE,
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
                        _ACTIVE,
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

    def delete_for_user(self, user_id: UserId, *, keep: str | None = None) -> int:
        stmt = delete(SessionRow).where(SessionRow.user_id == user_id)
        if keep is not None:
            stmt = stmt.where(SessionRow.token_hash != keep)
        result = self._s.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    def delete_all(self) -> int:
        result = self._s.execute(delete(SessionRow))
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

    def get(self, household_id: WorkspaceId, scope: str, merchant: str) -> CategoryRule | None:
        row = self._s.get(CategoryRuleRow, (household_id, scope, merchant))
        if row is None:
            return None
        return CategoryRule(
            WorkspaceId(row.household_id), row.merchant, CategoryId(row.category_id), row.scope
        )

    def delete(self, household_id: WorkspaceId, scope: str, merchant: str) -> None:
        self._s.execute(
            delete(CategoryRuleRow).where(
                CategoryRuleRow.household_id == household_id,
                CategoryRuleRow.scope == scope,
                CategoryRuleRow.merchant == merchant,
            )
        )


class SqlIdeaDismissalRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def dismissed(self, household_id: WorkspaceId) -> set[str]:
        return set(
            self._s.scalars(
                select(DismissedIdeaRow.idea_id).where(
                    DismissedIdeaRow.household_id == household_id
                )
            )
        )

    def dismiss(self, household_id: WorkspaceId, idea_id: str, user_id: UserId) -> None:
        if self._s.get(DismissedIdeaRow, (household_id, idea_id)) is None:
            self._s.add(
                DismissedIdeaRow(household_id=household_id, idea_id=idea_id, dismissed_by=user_id)
            )
            _flush(self._s)

    def restore(self, household_id: WorkspaceId, idea_id: str) -> None:
        self._s.execute(
            delete(DismissedIdeaRow).where(
                DismissedIdeaRow.household_id == household_id, DismissedIdeaRow.idea_id == idea_id
            )
        )
        _flush(self._s)


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

    def set_status(self, batch_id: UUID, status: ImportStatus) -> None:
        self._s.execute(
            update(ImportBatchRow).where(ImportBatchRow.id == batch_id).values(status=status.value)
        )

    def committed(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> list[ImportBatch]:
        """Confirmadas y deshechas de esas cuentas, de la más reciente a la más antigua."""
        if not account_ids:
            return []
        rows = self._s.scalars(
            select(ImportBatchRow)
            .where(
                ImportBatchRow.household_id == household_id,
                ImportBatchRow.account_id.in_(account_ids),
                ImportBatchRow.status != ImportStatus.PREVIEW.value,
            )
            .order_by(ImportBatchRow.committed_at.desc(), ImportBatchRow.created_at.desc())
        )
        return [_batch(r) for r in rows]

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

    def purge_expired_content(self, now: datetime) -> int:
        result = self._s.execute(
            update(ImportBatchRow)
            .where(
                ImportBatchRow.status == ImportStatus.PREVIEW.value,
                ImportBatchRow.created_at < now - PREVIEW_TTL,
                ImportBatchRow.content.is_not(None),
            )
            .values(content=None)
        )
        return int(getattr(result, "rowcount", 0) or 0)

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


class SqlMemberPatternRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[MemberPattern]:
        rows = self._s.scalars(
            select(MemberPatternRow)
            .where(MemberPatternRow.household_id == household_id)
            .order_by(MemberPatternRow.direction, MemberPatternRow.pattern)
        )
        return [
            MemberPattern(
                WorkspaceId(r.household_id),
                UserId(r.user_id),
                r.pattern,
                PatternDirection(r.direction),
            )
            for r in rows
        ]

    def add(self, pattern: MemberPattern, now: datetime) -> None:
        key = (pattern.household_id, pattern.direction.value, pattern.pattern)
        if self._s.get(MemberPatternRow, key) is not None:
            raise ConflictError("Ese patrón ya está guardado")
        self._s.add(
            MemberPatternRow(
                household_id=pattern.household_id,
                direction=pattern.direction.value,
                pattern=pattern.pattern,
                user_id=pattern.user_id,
                created_at=now,
            )
        )
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, direction: PatternDirection, pattern: str) -> bool:
        result = self._s.execute(
            delete(MemberPatternRow).where(
                MemberPatternRow.household_id == household_id,
                MemberPatternRow.direction == direction.value,
                MemberPatternRow.pattern == pattern,
            )
        )
        return bool(getattr(result, "rowcount", 0))


def _operation(row: ChangeOperationRow, entries: list[ChangeEntryRow]) -> Operation:
    return Operation(
        id=row.id,
        household_id=WorkspaceId(row.household_id),
        actor_id=UserId(row.actor_id),
        created_at=_as_utc(row.created_at),
        action=row.action,
        summary=row.summary,
        changes=tuple(
            Change(
                Entity(e.entity), e.entity_id, e.field, json.loads(e.before), json.loads(e.after)
            )
            for e in sorted(entries, key=lambda e: e.position)
        ),
        undone_at=_as_utc(row.undone_at) if row.undone_at else None,
        undone_by=UserId(row.undone_by) if row.undone_by else None,
    )


class SqlChangeRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, operation: Operation) -> None:
        o = operation
        self._s.add(
            ChangeOperationRow(
                id=o.id,
                household_id=o.household_id,
                actor_id=o.actor_id,
                created_at=o.created_at,
                action=o.action,
                summary=o.summary,
            )
        )
        self._s.flush()
        self._s.add_all(
            ChangeEntryRow(
                operation_id=o.id,
                position=i,
                entity=c.entity.value,
                entity_id=c.entity_id,
                field=c.field,
                before=json.dumps(c.before),
                after=json.dumps(c.after),
            )
            for i, c in enumerate(o.changes)
        )
        _flush(self._s)

    def _entries(self, ids: list[UUID]) -> dict[UUID, list[ChangeEntryRow]]:
        out: dict[UUID, list[ChangeEntryRow]] = {i: [] for i in ids}
        for i in range(0, len(ids), 500):
            for e in self._s.scalars(
                select(ChangeEntryRow).where(ChangeEntryRow.operation_id.in_(ids[i : i + 500]))
            ):
                out[e.operation_id].append(e)
        return out

    def get(self, household_id: WorkspaceId, operation_id: UUID) -> Operation | None:
        row = self._s.scalar(
            select(ChangeOperationRow).where(
                ChangeOperationRow.id == operation_id,
                ChangeOperationRow.household_id == household_id,
            )
        )
        return _operation(row, self._entries([row.id])[row.id]) if row else None

    def for_actor(self, household_id: WorkspaceId, actor_id: UserId, limit: int) -> list[Operation]:
        rows = list(
            self._s.scalars(
                select(ChangeOperationRow)
                .where(
                    ChangeOperationRow.household_id == household_id,
                    ChangeOperationRow.actor_id == actor_id,
                )
                .order_by(ChangeOperationRow.created_at.desc())
                .limit(limit)
            )
        )
        entries = self._entries([r.id for r in rows])
        return [_operation(r, entries[r.id]) for r in rows]

    def touching(
        self, household_id: WorkspaceId, entity: Entity, entity_ids: list[str]
    ) -> list[Operation]:
        """Operaciones que cambian alguna de esas entidades, de la más antigua a la más reciente."""
        if not entity_ids:
            return []
        op_ids: set[UUID] = set()
        for i in range(0, len(entity_ids), 500):
            op_ids.update(
                self._s.scalars(
                    select(ChangeEntryRow.operation_id)
                    .join(ChangeOperationRow, ChangeOperationRow.id == ChangeEntryRow.operation_id)
                    .where(
                        ChangeOperationRow.household_id == household_id,
                        ChangeEntryRow.entity == entity.value,
                        ChangeEntryRow.entity_id.in_(entity_ids[i : i + 500]),
                    )
                )
            )
        if not op_ids:
            return []
        rows = list(
            self._s.scalars(
                select(ChangeOperationRow)
                .where(ChangeOperationRow.id.in_(op_ids))
                .order_by(ChangeOperationRow.created_at)
            )
        )
        entries = self._entries([r.id for r in rows])
        return [_operation(r, entries[r.id]) for r in rows]

    def mark_undone(
        self, operation_id: UUID, undone_at: datetime | None, undone_by: UserId | None
    ) -> None:
        self._s.execute(
            update(ChangeOperationRow)
            .where(ChangeOperationRow.id == operation_id)
            .values(undone_at=undone_at, undone_by=undone_by)
        )


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
        self.dismissed_ideas = SqlIdeaDismissalRepository(session)
        self.member_patterns = SqlMemberPatternRepository(session)
        self.changes = SqlChangeRepository(session)

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "Los datos han cambiado mientras guardabas; vuelve a intentarlo"
            ) from exc
