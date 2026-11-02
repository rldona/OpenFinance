from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from openfinance.infrastructure.db.base import Base

AMOUNT = Numeric(19, 4)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HouseholdRow(Base):
    __tablename__ = "households"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MembershipRow(Base):
    __tablename__ = "memberships"

    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccountRow(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("(kind = 'personal') = (owner_id IS NOT NULL)", name="personal_owner"),
        CheckConstraint(
            "type IN ('bank', 'cash', 'card', 'loan', 'investment')", name="type_valid"
        ),
        UniqueConstraint("id", "household_id", name="uq_accounts_id_household"),
        # El titular de una cuenta personal tiene que ser miembro del mismo hogar.
        ForeignKeyConstraint(
            ["household_id", "owner_id"],
            ["memberships.household_id", "memberships.user_id"],
            name="fk_accounts_owner_membership",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    institution: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))
    type: Mapped[str] = mapped_column(String(20), default="bank", server_default="bank")
    currency: Mapped[str] = mapped_column(String(3))
    opening_balance: Mapped[Decimal] = mapped_column(AMOUNT)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TransactionRow(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "fingerprint", name="uq_transactions_account_fingerprint"),
        CheckConstraint("amount <> 0", name="amount_not_zero"),
        # La cuenta del movimiento es del mismo hogar que el movimiento.
        ForeignKeyConstraint(
            ["account_id", "household_id"],
            ["accounts.id", "accounts.household_id"],
            name="fk_transactions_account_household",
        ),
        # Quien aporta es miembro del mismo hogar.
        ForeignKeyConstraint(
            ["household_id", "member_id"],
            ["memberships.household_id", "memberships.user_id"],
            name="fk_transactions_member_membership",
        ),
        Index("ix_transactions_household_booked_at", "household_id", "booked_at"),
        Index("ix_transactions_household_merchant", "household_id", "merchant"),
        ForeignKeyConstraint(
            ["category_id", "household_id"],
            ["categories.id", "categories.household_id"],
            name="fk_transactions_category_household",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"))
    account_id: Mapped[UUID] = mapped_column(index=True)
    booked_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    value_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(AMOUNT)
    currency: Mapped[str] = mapped_column(String(3))
    kind: Mapped[str] = mapped_column(String(30))
    category_id: Mapped[UUID | None] = mapped_column()
    merchant: Mapped[str] = mapped_column(String(100), default="")
    member_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    bank_type: Mapped[str] = mapped_column(String(40), default="")
    source: Mapped[str] = mapped_column(String(200), default="manual")
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    import_id: Mapped[UUID | None] = mapped_column(ForeignKey("import_batches.id"), index=True)
    note: Mapped[str] = mapped_column(String(2000), default="", server_default="")
    voided: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CategoryRow(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("household_id", "key", name="uq_categories_household_key"),
        UniqueConstraint("id", "household_id", name="uq_categories_id_household"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    key: Mapped[str] = mapped_column(String(50))
    icon: Mapped[str] = mapped_column(String(16))
    color: Mapped[str] = mapped_column(String(7))
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    slug: Mapped[str | None] = mapped_column(String(30))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CategoryRuleRow(Base):
    __tablename__ = "category_rules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["category_id", "household_id"],
            ["categories.id", "categories.household_id"],
            name="fk_category_rules_category_household",
        ),
    )

    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), primary_key=True)
    scope: Mapped[str] = mapped_column(String(36), primary_key=True)
    merchant: Mapped[str] = mapped_column(String(100), primary_key=True)
    category_id: Mapped[UUID] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DismissedIdeaRow(Base):
    """Ideas de ahorro que el hogar ha descartado (OF-806)."""

    __tablename__ = "dismissed_ideas"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "dismissed_by"],
            ["memberships.household_id", "memberships.user_id"],
            name="fk_dismissed_ideas_member_membership",
        ),
    )

    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), primary_key=True)
    idea_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    dismissed_by: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TransactionTagRow(Base):
    """Etiqueta de un movimiento (OF-1002). Hereda la visibilidad del movimiento."""

    __tablename__ = "transaction_tags"
    __table_args__ = (Index("ix_transaction_tags_household_key", "household_id", "tag_key"),)

    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True
    )
    tag_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"))
    tag: Mapped[str] = mapped_column(String(40))


class TransactionSplitRow(Base):
    """Parte de un movimiento dividido (OF-1003)."""

    __tablename__ = "transaction_splits"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="amount_not_zero"),
        ForeignKeyConstraint(
            ["category_id", "household_id"],
            ["categories.id", "categories.household_id"],
            name="fk_transaction_splits_category_household",
        ),
    )

    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"))
    amount: Mapped[Decimal] = mapped_column(AMOUNT)
    currency: Mapped[str] = mapped_column(String(3))
    category_id: Mapped[UUID] = mapped_column()


class TransactionLinkRow(Base):
    """Un lado de un traspaso enlazado: cada enlace son dos filas, una por lado (OF-1004)."""

    __tablename__ = "transaction_links"
    __table_args__ = (CheckConstraint("transaction_id <> peer_id", name="not_self"),)

    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True
    )
    peer_id: Mapped[UUID] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"))
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"))


class MerchantRow(Base):
    """Comercio con nombre propio (OF-1001). Los que nadie ha tocado no tienen fila."""

    __tablename__ = "merchants"
    __table_args__ = (UniqueConstraint("id", "household_id", name="uq_merchants_id_household"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"))
    name: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MerchantKeyRow(Base):
    """Variante del banco («MERCADONA») que pertenece a un comercio."""

    __tablename__ = "merchant_keys"
    __table_args__ = (
        ForeignKeyConstraint(
            ["merchant_id", "household_id"],
            ["merchants.id", "merchants.household_id"],
            name="fk_merchant_keys_merchant_household",
            ondelete="CASCADE",
        ),
        Index("ix_merchant_keys_merchant", "merchant_id"),
    )

    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    merchant_id: Mapped[UUID] = mapped_column()


class BudgetRow(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["category_id", "household_id"],
            ["categories.id", "categories.household_id"],
            name="fk_budgets_category_household",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), primary_key=True)
    category_id: Mapped[UUID] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(AMOUNT)
    currency: Mapped[str] = mapped_column(String(3))


class GoalRow(Base):
    __tablename__ = "goals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "household_id"],
            ["accounts.id", "accounts.household_id"],
            name="fk_goals_account_household",
        ),
        CheckConstraint("target > 0", name="target_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    icon: Mapped[str] = mapped_column(String(16))
    target: Mapped[Decimal] = mapped_column(AMOUNT)
    monthly: Mapped[Decimal] = mapped_column(AMOUNT)
    saved: Mapped[Decimal] = mapped_column(AMOUNT)
    currency: Mapped[str] = mapped_column(String(3))
    deadline: Mapped[str | None] = mapped_column(String(7))
    account_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportBatchRow(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "household_id"],
            ["accounts.id", "accounts.household_id"],
            name="fk_import_batches_account_household",
        ),
        Index("ix_import_batches_household_created_at", "household_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"))
    account_id: Mapped[UUID] = mapped_column()
    filename: Mapped[str] = mapped_column(String(200))
    content: Mapped[bytes | None] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)


class MemberPatternRow(Base):
    """Texto del concepto bancario que identifica la aportación de una persona."""

    __tablename__ = "member_patterns"
    __table_args__ = (
        CheckConstraint("direction IN ('inflow', 'outflow')", name="direction_valid"),
        CheckConstraint("length(pattern) >= 3", name="pattern_min_length"),
        ForeignKeyConstraint(
            ["household_id", "user_id"],
            ["memberships.household_id", "memberships.user_id"],
            name="fk_member_patterns_member_membership",
        ),
    )

    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"), primary_key=True)
    direction: Mapped[str] = mapped_column(String(10), primary_key=True)
    pattern: Mapped[str] = mapped_column(String(60), primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SessionRow(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChangeOperationRow(Base):
    """Una acción de una persona en el registro de cambios (ADR-0017)."""

    __tablename__ = "change_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "actor_id"],
            ["memberships.household_id", "memberships.user_id"],
            name="fk_change_operations_actor_membership",
        ),
        Index("ix_change_operations_household_actor", "household_id", "actor_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"))
    actor_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(String(200))
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    undone_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class ChangeEntryRow(Base):
    __tablename__ = "change_entries"
    __table_args__ = (
        Index("ix_change_entries_entity", "entity", "entity_id"),
        CheckConstraint(
            "entity IN ('transaction', 'rule', 'import', 'merchant', 'tag', 'split', 'link', "
            "'account', 'attachment', 'reconciliation', 'rate')",
            name="entity_valid",
        ),
    )

    operation_id: Mapped[UUID] = mapped_column(
        ForeignKey("change_operations.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[str] = mapped_column(String(150))
    field: Mapped[str] = mapped_column(String(30))
    before: Mapped[str] = mapped_column(String(600))
    """Valor anterior en JSON (``null``, ``true``, ``"texto"``)."""
    after: Mapped[str] = mapped_column(String(600))
