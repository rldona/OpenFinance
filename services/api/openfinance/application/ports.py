"""Interfaces que la capa de aplicación necesita de la infraestructura."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from openfinance.domain.categories import Category, CategoryId, CategoryRule
from openfinance.domain.identity import User
from openfinance.domain.imports import (
    ClassificationRules,
    MemberPattern,
    ParseResult,
    PatternDirection,
)
from openfinance.domain.imports.batch import ImportBatch
from openfinance.domain.ledger import Account, Institution, Transaction
from openfinance.domain.savings import Budget, Goal, GoalId
from openfinance.domain.shared.ids import AccountId, TransactionId, UserId, WorkspaceId
from openfinance.domain.workspaces import Household


@dataclass(frozen=True, slots=True)
class TransactionQuery:
    year: int | None = None
    month: int | None = None
    text: str | None = None
    uncategorized: bool = False
    account_id: AccountId | None = None
    category_id: CategoryId | None = None
    shared_only: bool = False
    """Solo cuentas del hogar (conjunta y huchas), como los gráficos."""
    limit: int = 1000

    def __post_init__(self) -> None:
        if (self.year is None) != (self.month is None):
            raise ValueError("Indica año y mes a la vez")
        if self.month is not None and not 1 <= self.month <= 12:
            raise ValueError("Mes no válido")
        if not 1 <= self.limit <= 5000:
            raise ValueError("Límite no válido")


@dataclass(frozen=True, slots=True)
class StoredSession:
    token_hash: str
    user_id: UserId
    household_id: WorkspaceId
    expires_at: datetime


class UserRepository(Protocol):
    def get(self, user_id: UserId) -> User | None: ...
    def get_by_email(self, email: str) -> User | None: ...
    def add(self, user: User) -> None: ...


class HouseholdRepository(Protocol):
    def get(self, household_id: WorkspaceId) -> Household | None: ...
    def add(self, household: Household) -> None: ...
    def add_member(self, household_id: WorkspaceId, user_id: UserId) -> None: ...
    def households_of(self, user_id: UserId) -> list[WorkspaceId]: ...
    def members(self, household_id: WorkspaceId) -> list[User]: ...


class AccountRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[Account]: ...
    def add(self, account: Account) -> None: ...


class TransactionRepository(Protocol):
    def search(
        self, household_id: WorkspaceId, account_ids: list[AccountId], query: TransactionQuery
    ) -> list[Transaction]: ...
    def for_account(
        self, household_id: WorkspaceId, account_id: AccountId
    ) -> list[Transaction]: ...
    def add(self, transaction: Transaction) -> None: ...
    def get(
        self, household_id: WorkspaceId, transaction_id: TransactionId
    ) -> Transaction | None: ...
    def set_category(
        self, household_id: WorkspaceId, ids: list[TransactionId], category_id: CategoryId | None
    ) -> None: ...
    def uncategorized_with_merchant_word(
        self, household_id: WorkspaceId, account_ids: list[AccountId], first_word: str
    ) -> list[Transaction]:
        """Gastos sin categoría cuyo comercio empieza por esa palabra."""
        ...

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
        """Con ``only_category``, solo los de ``category_id`` (``None`` = sin categoría)."""
        ...

    def first_booked_at(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> datetime | None: ...
    def count_uncategorized(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> int: ...
    def existing_fingerprints(
        self, household_id: WorkspaceId, account_id: AccountId, fingerprints: list[str]
    ) -> set[str]: ...


class CategoryRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[Category]: ...
    def get(self, household_id: WorkspaceId, category_id: CategoryId) -> Category | None: ...
    def add(self, category: Category) -> None: ...
    def update(self, category: Category) -> None: ...


class RuleRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[CategoryRule]: ...
    def upsert(self, rule: CategoryRule, now: datetime) -> None: ...
    def delete(self, household_id: WorkspaceId, scope: str, merchant: str) -> None: ...


class BudgetRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[Budget]: ...
    def upsert(self, budget: Budget) -> None: ...
    def delete(self, household_id: WorkspaceId, category_id: CategoryId) -> None: ...


class GoalRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[Goal]: ...
    def get(self, household_id: WorkspaceId, goal_id: GoalId) -> Goal | None: ...
    def add(self, goal: Goal) -> None: ...
    def update(self, goal: Goal) -> None: ...
    def delete(self, household_id: WorkspaceId, goal_id: GoalId) -> None: ...


class ImportBatchRepository(Protocol):
    def add(self, batch: ImportBatch, content: bytes) -> None: ...
    def get(self, household_id: WorkspaceId, batch_id: UUID) -> ImportBatch | None: ...
    def content(self, batch_id: UUID) -> bytes | None: ...
    def claim(self, batch_id: UUID) -> bool:
        """Pasa el lote de vista previa a confirmado si nadie lo ha hecho antes."""
        ...

    def purge_expired_content(self, now: datetime) -> None: ...
    def save_committed(self, batch: ImportBatch) -> None:
        """Guarda el resultado y borra el contenido del archivo, que ya no hace falta."""
        ...


class MemberPatternRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[MemberPattern]: ...
    def add(self, pattern: MemberPattern, now: datetime) -> None:
        """Un patrón repetido (mismo hogar, sentido y texto) es un ConflictError."""
        ...

    def delete(
        self, household_id: WorkspaceId, direction: PatternDirection, pattern: str
    ) -> bool: ...


class StatementParser(Protocol):
    def __call__(
        self, content: bytes, account_key: str, rules: ClassificationRules
    ) -> ParseResult: ...


class StatementParsers(Protocol):
    def get(self, institution: Institution) -> StatementParser | None: ...


class SessionRepository(Protocol):
    def add(self, session: StoredSession) -> None: ...
    def get(self, token_hash: str) -> StoredSession | None: ...
    def delete(self, token_hash: str) -> None: ...
    def delete_expired(self, now: datetime) -> int: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password_hash: str, password: str) -> bool: ...
    def dummy_verify(self, password: str) -> None:
        """Gasta el mismo tiempo que ``verify`` para no revelar si un email existe."""
        ...


class UnitOfWork(Protocol):
    @property
    def users(self) -> UserRepository: ...
    @property
    def households(self) -> HouseholdRepository: ...
    @property
    def accounts(self) -> AccountRepository: ...
    @property
    def transactions(self) -> TransactionRepository: ...
    @property
    def sessions(self) -> SessionRepository: ...
    @property
    def imports(self) -> ImportBatchRepository: ...
    @property
    def categories(self) -> CategoryRepository: ...
    @property
    def rules(self) -> RuleRepository: ...
    @property
    def budgets(self) -> BudgetRepository: ...
    @property
    def goals(self) -> GoalRepository: ...
    @property
    def member_patterns(self) -> MemberPatternRepository: ...

    def commit(self) -> None:
        """Confirma la transacción. Un conflicto de integridad se traduce en ConflictError."""
        ...
