"""Interfaces que la capa de aplicación necesita de la infraestructura."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from openfinance.domain.identity import User
from openfinance.domain.imports import ClassificationRules, ParseResult
from openfinance.domain.imports.batch import ImportBatch
from openfinance.domain.ledger import Account, Institution, Transaction
from openfinance.domain.shared.ids import AccountId, UserId, WorkspaceId
from openfinance.domain.workspaces import Household


@dataclass(frozen=True, slots=True)
class TransactionQuery:
    year: int | None = None
    month: int | None = None
    text: str | None = None
    uncategorized: bool = False
    account_id: AccountId | None = None
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
    def existing_fingerprints(
        self, household_id: WorkspaceId, account_id: AccountId, fingerprints: list[str]
    ) -> set[str]: ...


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

    def commit(self) -> None:
        """Confirma la transacción. Un conflicto de integridad se traduce en ConflictError."""
        ...
