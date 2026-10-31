from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from openfinance.application.imports import ImportPreview, ImportResult
from openfinance.domain.identity import User
from openfinance.domain.ledger import (
    Account,
    AccountKind,
    Institution,
    Transaction,
    TransactionKind,
)
from openfinance.domain.shared import Money
from openfinance.domain.workspaces import Household


class MoneyOut(BaseModel):
    amount: str = Field(examples=["-87.34"], description="Decimal exacto como texto")
    currency: str = Field(examples=["EUR"])

    @classmethod
    def of(cls, money: Money) -> MoneyOut:
        return cls(amount=str(money.amount), currency=money.currency.code)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    id: UUID
    email: str
    display_name: str

    @classmethod
    def of(cls, user: User) -> UserOut:
        return cls(id=user.id, email=user.email, display_name=user.display_name)


class MemberOut(BaseModel):
    id: UUID
    display_name: str


class HouseholdOut(BaseModel):
    id: UUID
    name: str
    currency: str

    @classmethod
    def of(cls, household: Household) -> HouseholdOut:
        return cls(id=household.id, name=household.name, currency=household.currency.code)


class MeOut(BaseModel):
    user: UserOut
    household: HouseholdOut
    members: list[MemberOut]


class AccountOut(BaseModel):
    id: UUID
    name: str
    institution: Institution
    kind: AccountKind
    owner_id: UUID | None
    opening_balance: MoneyOut
    balance: MoneyOut

    @classmethod
    def of(cls, account: Account, balance: Money) -> AccountOut:
        return cls(
            id=account.id,
            name=account.name,
            institution=account.institution,
            kind=account.kind,
            owner_id=account.owner_id,
            opening_balance=MoneyOut.of(account.opening_balance),
            balance=MoneyOut.of(balance),
        )


class TransactionOut(BaseModel):
    id: UUID
    account_id: UUID
    booked_at: datetime
    value_date: date
    description: str
    amount: MoneyOut
    kind: TransactionKind
    category: str | None
    member_id: UUID | None
    source: str

    @classmethod
    def of(cls, t: Transaction) -> TransactionOut:
        return cls(
            id=t.id,
            account_id=t.account_id,
            booked_at=t.booked_at,
            value_date=t.value_date,
            description=t.description,
            amount=MoneyOut.of(t.amount),
            kind=t.kind,
            category=t.category,
            member_id=t.member_id,
            source=t.source,
        )


class PreviewRowOut(BaseModel):
    line: int
    booked_at: datetime
    description: str
    amount: MoneyOut
    kind: TransactionKind
    member_id: UUID | None
    duplicate: bool


class SkippedRowOut(BaseModel):
    line: int
    reason: str
    description: str


class BalanceMismatchOut(BaseModel):
    line: int
    expected: MoneyOut
    reported: MoneyOut


class ImportPreviewOut(BaseModel):
    id: UUID
    account_id: UUID
    filename: str
    new_count: int
    duplicate_count: int
    skipped_count: int
    rows: list[PreviewRowOut]
    skipped: list[SkippedRowOut]
    balance_mismatches: list[BalanceMismatchOut]
    bank_balance: MoneyOut | None
    balance_after_import: MoneyOut

    @classmethod
    def of(cls, p: ImportPreview) -> ImportPreviewOut:
        return cls(
            id=p.batch.id,
            account_id=p.account.id,
            filename=p.batch.filename,
            new_count=p.new_count,
            duplicate_count=p.duplicate_count,
            skipped_count=len(p.skipped),
            rows=[
                PreviewRowOut(
                    line=r.row.line,
                    booked_at=r.row.booked_at,
                    description=r.row.description,
                    amount=MoneyOut.of(r.row.amount),
                    kind=r.row.suggested_kind
                    if r.member_id or r.row.suggested_kind is not TransactionKind.CONTRIBUTION
                    else TransactionKind.INCOME,
                    member_id=r.member_id,
                    duplicate=r.duplicate,
                )
                for r in p.rows
            ],
            skipped=[
                SkippedRowOut(line=x.line, reason=x.reason, description=x.description)
                for x in p.skipped
            ],
            balance_mismatches=[
                BalanceMismatchOut(
                    line=m.line, expected=MoneyOut.of(m.expected), reported=MoneyOut.of(m.reported)
                )
                for m in p.balance_mismatches
            ],
            bank_balance=MoneyOut.of(p.bank_balance) if p.bank_balance else None,
            balance_after_import=MoneyOut.of(p.balance_after_import),
        )


class ImportResultOut(BaseModel):
    id: UUID
    status: str
    created: int
    duplicates: int
    skipped: int

    @classmethod
    def of(cls, r: ImportResult) -> ImportResultOut:
        return cls(
            id=r.batch.id,
            status=r.batch.status.value,
            created=r.created,
            duplicates=r.duplicates,
            skipped=r.skipped,
        )
