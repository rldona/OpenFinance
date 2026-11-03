"""Interfaces que la capa de aplicación necesita de la infraestructura."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from openfinance.domain.attachments import Attachment
from openfinance.domain.automation import AutomationRule
from openfinance.domain.categories import Category, CategoryId, CategoryRule
from openfinance.domain.changes import Entity, Operation
from openfinance.domain.csv_profile import CsvProfile, CsvSample
from openfinance.domain.identity import User
from openfinance.domain.imports import (
    ClassificationRules,
    MemberPattern,
    ParseResult,
    PatternDirection,
)
from openfinance.domain.imports.batch import ImportBatch, ImportStatus
from openfinance.domain.insights import Month
from openfinance.domain.ledger import Account, Institution, Transaction
from openfinance.domain.merchants import Merchant, MerchantId
from openfinance.domain.notifications import (
    NotificationPrefs,
    PushMessage,
    PushSubscription,
    SendResult,
)
from openfinance.domain.rates import ExchangeRate
from openfinance.domain.reconciliation import Reconciliation
from openfinance.domain.savings import Budget, Goal, GoalContribution, GoalId
from openfinance.domain.schedule import ScheduledPayment
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, TransactionId, UserId, WorkspaceId
from openfinance.domain.splits import SplitPart
from openfinance.domain.templates import TransactionTemplate
from openfinance.domain.workspaces import Household


@dataclass(frozen=True, slots=True)
class TransactionQuery:
    year: int | None = None
    month: int | None = None
    text: str | None = None
    uncategorized: bool = False
    account_id: AccountId | None = None
    category_id: CategoryId | None = None
    tag: str | None = None
    """Solo los movimientos con esta etiqueta (OF-1002)."""
    reviewed: bool | None = None
    """Solo los revisados o solo los sin revisar (OF-1006)."""
    shared_only: bool = False
    """Solo cuentas del hogar (conjunta y huchas), como los gráficos."""
    mine_only: bool = False
    """Solo las cuentas personales de quien pregunta, como la vista «mío»."""
    limit: int = 1000
    after: tuple[datetime, UUID] | None = None
    """Cursor (OF-803): solo los movimientos posteriores a este en el orden del listado."""

    def __post_init__(self) -> None:
        if (self.year is None) != (self.month is None):
            raise ValueError("Indica año y mes a la vez")
        if self.shared_only and self.mine_only:
            raise ValueError("Elige solo cuentas del hogar o solo las tuyas")
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


class AlertRepository(Protocol):
    """Qué avisos ha descartado cada persona (OF-1301). Los avisos en sí no se guardan."""

    def dismissed(self, user_id: UserId) -> set[str]: ...
    def dismiss(self, user_id: UserId, key: str, at: datetime) -> None: ...


class NotificationRepository(Protocol):
    """Suscripciones push, preferencias y lo ya notificado, por persona (OF-1302)."""

    def subscriptions(self, user_id: UserId) -> list[PushSubscription]: ...
    def subscribe(self, user_id: UserId, subscription: PushSubscription, at: datetime) -> None:
        """Alta o cambio de dueño: un dispositivo pertenece a quien inició sesión en él."""
        ...

    def unsubscribe(self, user_id: UserId, endpoint: str) -> bool: ...
    def drop_endpoint(self, endpoint: str) -> None: ...
    def prefs(self, user_id: UserId) -> NotificationPrefs: ...
    def save_prefs(self, user_id: UserId, prefs: NotificationPrefs) -> None: ...
    def delivered(self, user_id: UserId) -> set[str]: ...
    def mark_delivered(self, user_id: UserId, keys: list[str], at: datetime) -> None: ...


class PushSender(Protocol):
    """Envía una notificación a una suscripción (Web Push)."""

    @property
    def enabled(self) -> bool: ...
    def send(self, subscription: PushSubscription, message: PushMessage) -> SendResult: ...


class UserRepository(Protocol):
    def get(self, user_id: UserId) -> User | None: ...
    def get_by_email(self, email: str) -> User | None: ...
    def add(self, user: User) -> None: ...
    def set_password_hash(self, user_id: UserId, password_hash: str) -> None: ...


class HouseholdRepository(Protocol):
    def get(self, household_id: WorkspaceId) -> Household | None: ...
    def add(self, household: Household) -> None: ...
    def add_member(self, household_id: WorkspaceId, user_id: UserId) -> None: ...
    def households_of(self, user_id: UserId) -> list[WorkspaceId]: ...
    def all_ids(self) -> list[WorkspaceId]: ...
    def members(self, household_id: WorkspaceId) -> list[User]: ...


class AccountRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[Account]: ...
    def add(self, account: Account) -> None: ...


class TransactionRepository(Protocol):
    def search(
        self, household_id: WorkspaceId, account_ids: list[AccountId], query: TransactionQuery
    ) -> list[Transaction]: ...
    def totals(
        self, household_id: WorkspaceId, account_ids: list[AccountId], query: TransactionQuery
    ) -> tuple[int, dict[str, Decimal]]:
        """Cuántos movimientos cumplen el filtro (sin cursor ni límite) y cuánto suman, por
        moneda."""
        ...

    def for_account(
        self, household_id: WorkspaceId, account_id: AccountId
    ) -> list[Transaction]: ...
    def balances(
        self,
        household_id: WorkspaceId,
        account_ids: list[AccountId],
        until: datetime | None = None,
    ) -> dict[AccountId, Decimal]:
        """Suma de los movimientos activos de cada cuenta (sin el saldo inicial), calculada
        en la base de datos, hasta ``until`` si se indica. Sin movimientos = no aparece."""
        ...

    def add(self, transaction: Transaction) -> None: ...
    def add_many(self, transactions: list[Transaction]) -> None:
        """Inserta varios movimientos con un solo flush."""
        ...

    def get(
        self,
        household_id: WorkspaceId,
        transaction_id: TransactionId,
        *,
        include_voided: bool = False,
    ) -> Transaction | None:
        """Los anulados solo se devuelven con ``include_voided`` (para deshacer)."""
        ...

    def save(self, transaction: Transaction) -> None:
        """Guarda los campos corregibles: tipo, persona, categoría, nota, anulación."""
        ...

    def for_import(self, household_id: WorkspaceId, import_id: UUID) -> list[Transaction]: ...
    def accounts_of(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, AccountId]:
        """La cuenta de cada movimiento, también de los anulados."""
        ...

    def voided_with_fingerprints(
        self, household_id: WorkspaceId, account_id: AccountId, fingerprints: list[str]
    ) -> dict[str, Transaction]: ...
    def set_category(
        self, household_id: WorkspaceId, ids: list[TransactionId], category_id: CategoryId | None
    ) -> None: ...
    def transfer_candidates(
        self,
        household_id: WorkspaceId,
        account_ids: list[AccountId],
        transaction: Transaction,
        days: int,
    ) -> list[Transaction]:
        """Movimientos de otras cuentas con el importe contrario y fecha cercana, sin enlazar."""
        ...

    def merchant_totals(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> list[tuple[str, int, Decimal]]:
        """(variante, cuántos movimientos, suma) por variante, solo de esas cuentas (OF-1001)."""
        ...

    def uncategorized_with_merchant(
        self, household_id: WorkspaceId, account_ids: list[AccountId], key: str
    ) -> list[Transaction]:
        """Gastos sin categoría de exactamente esa variante."""
        ...

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
    def get(self, household_id: WorkspaceId, scope: str, merchant: str) -> CategoryRule | None: ...
    def delete(self, household_id: WorkspaceId, scope: str, merchant: str) -> None: ...


class CsvProfileRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[CsvProfile]: ...
    def get(self, household_id: WorkspaceId, profile_id: UUID) -> CsvProfile | None: ...
    def save(self, profile: CsvProfile, created_by: UserId) -> None: ...
    def delete(self, household_id: WorkspaceId, profile_id: UUID) -> None: ...


class ScheduleRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[ScheduledPayment]:
        """Todos los pagos del hogar, también los de cuentas personales: quien llama filtra."""
        ...

    def get(self, household_id: WorkspaceId, schedule_id: UUID) -> ScheduledPayment | None: ...
    def save(self, payment: ScheduledPayment, created_by: UserId) -> None: ...
    def delete(self, household_id: WorkspaceId, schedule_id: UUID) -> None: ...


class TemplateRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[TransactionTemplate]:
        """Todas las plantillas del hogar, también las personales: quien llama filtra."""
        ...

    def get(self, household_id: WorkspaceId, template_id: UUID) -> TransactionTemplate | None: ...
    def save(self, template: TransactionTemplate, created_by: UserId) -> None: ...
    def delete(self, household_id: WorkspaceId, template_id: UUID) -> None: ...


class AutomationRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[AutomationRule]:
        """Todas las reglas del hogar, también las personales: quien llama filtra por ámbito."""
        ...

    def get(self, household_id: WorkspaceId, rule_id: UUID) -> AutomationRule | None: ...
    def save(self, rule: AutomationRule, created_by: UserId) -> None: ...
    def delete(self, household_id: WorkspaceId, rule_id: UUID) -> None: ...


class RateRepository(Protocol):
    def all(self, household_id: WorkspaceId) -> list[ExchangeRate]:
        """Todos los tipos del hogar, por moneda y fecha."""
        ...

    def get(
        self, household_id: WorkspaceId, currency: Currency, on: date
    ) -> ExchangeRate | None: ...
    def upsert(self, rate: ExchangeRate, created_by: UserId) -> None: ...
    def delete(self, household_id: WorkspaceId, currency: Currency, on: date) -> None: ...


class AttachmentRepository(Protocol):
    def add(self, attachment: Attachment) -> None: ...
    def get(self, household_id: WorkspaceId, attachment_id: UUID) -> Attachment | None:
        """Incluye los borrados (para poder deshacer)."""
        ...

    def for_transactions(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, list[Attachment]]:
        """Los adjuntos no borrados de cada movimiento, del más antiguo al más nuevo."""
        ...

    def set_deleted(
        self, household_id: WorkspaceId, attachment_id: UUID, deleted_at: datetime | None
    ) -> None: ...
    def deleted_before(self, cutoff: datetime) -> list[Attachment]:
        """Los borrados antes de esa fecha (de todos los hogares), para purgarlos del disco."""
        ...

    def erase(self, attachment_id: UUID) -> None:
        """Borra de verdad la fila de un adjunto ya purgado."""
        ...


class AttachmentStore(Protocol):
    """Dónde viven los archivos. Se identifican por el id del adjunto, nunca por su nombre."""

    def save(self, attachment_id: UUID, content: bytes) -> None: ...
    def read(self, attachment_id: UUID) -> bytes | None: ...
    def delete(self, attachment_id: UUID) -> None: ...


class ReconciliationRepository(Protocol):
    def add(self, reconciliation: Reconciliation) -> None: ...
    def for_account(
        self, household_id: WorkspaceId, account_id: AccountId, limit: int
    ) -> list[Reconciliation]:
        """Las últimas comprobaciones de la cuenta, de la más reciente a la más antigua."""
        ...


class LinkRepository(Protocol):
    def peers(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, TransactionId]:
        """El otro lado del traspaso de cada movimiento enlazado. Sin enlace = ausente."""
        ...

    def link(self, household_id: WorkspaceId, a: TransactionId, b: TransactionId) -> None: ...
    def unlink(self, household_id: WorkspaceId, a: TransactionId) -> None:
        """Quita el enlace de ``a`` y de su otro lado."""
        ...


class SplitRepository(Protocol):
    def for_transactions(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, list[SplitPart]]:
        """Las partes de cada movimiento dividido, en orden. Sin dividir = ausente."""
        ...

    def set(
        self, household_id: WorkspaceId, transaction_id: TransactionId, parts: list[SplitPart]
    ) -> None:
        """Sustituye las partes (lista vacía = deshacer la división)."""
        ...


class TagRepository(Protocol):
    def for_transactions(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, tuple[str, ...]]:
        """Las etiquetas de cada movimiento, en orden alfabético. Sin etiquetas = ausente."""
        ...

    def set(
        self, household_id: WorkspaceId, transaction_id: TransactionId, tags: tuple[str, ...]
    ) -> None: ...
    def counts(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> list[tuple[str, int]]:
        """(etiqueta, movimientos activos) solo de esas cuentas."""
        ...


class MerchantRepository(Protocol):
    def get(self, household_id: WorkspaceId, merchant_id: MerchantId) -> Merchant | None: ...
    def for_keys(self, household_id: WorkspaceId, keys: list[str]) -> dict[str, Merchant]:
        """Los comercios con nombre propio de esas variantes, por variante."""
        ...

    def all(self, household_id: WorkspaceId) -> list[Merchant]: ...
    def add(self, merchant: Merchant) -> None: ...
    def set_name(self, household_id: WorkspaceId, merchant_id: MerchantId, name: str) -> None: ...
    def set_keys(self, household_id: WorkspaceId, merchant_id: MerchantId, keys: list[str]) -> None:
        """Sustituye las variantes del comercio por estas."""
        ...

    def delete(self, household_id: WorkspaceId, merchant_id: MerchantId) -> None:
        """Borra el comercio y libera sus variantes."""
        ...


class BudgetRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[Budget]: ...
    def upsert(self, budget: Budget) -> None: ...
    def delete(self, household_id: WorkspaceId, category_id: CategoryId) -> None:
        """Borra el presupuesto y sus importes por mes."""
        ...

    def overrides(self, household_id: WorkspaceId) -> dict[tuple[CategoryId, Month], Money]:
        """Importes propios de un mes (OF-1203), por categoría y mes."""
        ...

    def set_override(
        self, household_id: WorkspaceId, category_id: CategoryId, month: Month, amount: Money
    ) -> None: ...
    def delete_override(
        self, household_id: WorkspaceId, category_id: CategoryId, month: Month
    ) -> None: ...


class IdeaDismissalRepository(Protocol):
    def dismissed(self, household_id: WorkspaceId) -> set[str]: ...
    def dismiss(self, household_id: WorkspaceId, idea_id: str, user_id: UserId) -> None: ...
    def restore(self, household_id: WorkspaceId, idea_id: str) -> None: ...


class GoalRepository(Protocol):
    def for_household(self, household_id: WorkspaceId) -> list[Goal]: ...
    def get(self, household_id: WorkspaceId, goal_id: GoalId) -> Goal | None: ...
    def add(self, goal: Goal) -> None: ...
    def update(self, goal: Goal) -> None: ...
    def delete(self, household_id: WorkspaceId, goal_id: GoalId) -> None:
        """Borra el objetivo y sus aportaciones."""
        ...

    def contributions(self, household_id: WorkspaceId, goal_id: GoalId) -> list[GoalContribution]:
        """Las aportaciones de un objetivo, de la más reciente a la más antigua."""
        ...

    def contribution_totals(self, household_id: WorkspaceId) -> dict[GoalId, Money]:
        """Lo aportado en cada objetivo que tiene aportaciones."""
        ...

    def get_contribution(
        self, household_id: WorkspaceId, contribution_id: UUID
    ) -> GoalContribution | None: ...
    def save_contribution(self, contribution: GoalContribution, created_by: UserId) -> None: ...
    def delete_contribution(self, household_id: WorkspaceId, contribution_id: UUID) -> None: ...


class ImportBatchRepository(Protocol):
    def add(self, batch: ImportBatch, content: bytes) -> None: ...
    def get(self, household_id: WorkspaceId, batch_id: UUID) -> ImportBatch | None: ...
    def content(self, batch_id: UUID) -> bytes | None: ...
    def set_status(self, batch_id: UUID, status: ImportStatus) -> None: ...
    def committed(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> list[ImportBatch]:
        """Confirmadas y deshechas, de la más reciente a la más antigua."""
        ...

    def claim(self, batch_id: UUID) -> bool:
        """Pasa el lote de vista previa a confirmado si nadie lo ha hecho antes."""
        ...

    def purge_expired_content(self, now: datetime) -> int:
        """Borra el archivo de las vistas previas caducadas. Devuelve cuántas."""
        ...

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
    def csv(self, profile: CsvProfile) -> StatementParser:
        """Lector de CSV guiado por un perfil (OF-1105)."""
        ...

    def csv_sample(self, content: bytes) -> CsvSample:
        """Separador y codificación propuestos y las primeras filas de un CSV."""
        ...


class SessionRepository(Protocol):
    def add(self, session: StoredSession) -> None: ...
    def get(self, token_hash: str) -> StoredSession | None: ...
    def delete(self, token_hash: str) -> None: ...
    def delete_expired(self, now: datetime) -> int: ...
    def delete_for_user(self, user_id: UserId, *, keep: str | None = None) -> int:
        """Cierra las sesiones de esa persona salvo la de hash ``keep``."""
        ...

    def delete_all(self) -> int:
        """Cierra todas las sesiones de la instalación (p. ej. tras restaurar una copia)."""
        ...


class ChangeRepository(Protocol):
    def add(self, operation: Operation) -> None: ...
    def get(self, household_id: WorkspaceId, operation_id: UUID) -> Operation | None: ...
    def for_actor(
        self, household_id: WorkspaceId, actor_id: UserId, limit: int
    ) -> list[Operation]: ...
    def touching(
        self, household_id: WorkspaceId, entity: Entity, entity_ids: list[str]
    ) -> list[Operation]:
        """Operaciones que cambian alguna de esas entidades, de la más antigua a la más reciente."""
        ...

    def mark_undone(
        self, operation_id: UUID, undone_at: datetime | None, undone_by: UserId | None
    ) -> None: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password_hash: str, password: str) -> bool: ...
    def dummy_verify(self, password: str) -> None:
        """Gasta el mismo tiempo que ``verify`` para no revelar si un email existe."""
        ...

    async def averify(self, password_hash: str | None, password: str) -> bool:
        """Como ``verify`` pero sin bloquear al llamante ni al grupo de hilos común (OF-906).
        Con ``None`` (no existe esa persona) gasta el mismo tiempo y devuelve ``False``."""
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
    def dismissed_ideas(self) -> IdeaDismissalRepository: ...
    @property
    def merchants(self) -> MerchantRepository: ...
    @property
    def tags(self) -> TagRepository: ...
    @property
    def splits(self) -> SplitRepository: ...
    @property
    def links(self) -> LinkRepository: ...
    @property
    def reconciliations(self) -> ReconciliationRepository: ...
    @property
    def attachments(self) -> AttachmentRepository: ...
    @property
    def rates(self) -> RateRepository: ...
    @property
    def automation(self) -> AutomationRepository: ...
    @property
    def csv_profiles(self) -> CsvProfileRepository: ...
    @property
    def schedule(self) -> ScheduleRepository: ...
    @property
    def templates(self) -> TemplateRepository: ...
    @property
    def alerts(self) -> AlertRepository: ...
    @property
    def notifications(self) -> NotificationRepository: ...
    @property
    def member_patterns(self) -> MemberPatternRepository: ...
    @property
    def changes(self) -> ChangeRepository: ...

    def commit(self) -> None:
        """Confirma la transacción. Un conflicto de integridad se traduce en ConflictError."""
        ...
