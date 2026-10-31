from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
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
    category: Mapped[str | None] = mapped_column(String(50))
    member_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    bank_type: Mapped[str] = mapped_column(String(40), default="")
    source: Mapped[str] = mapped_column(String(200), default="manual")
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    import_id: Mapped[UUID | None] = mapped_column(ForeignKey("import_batches.id"), index=True)
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


class SessionRow(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("households.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
