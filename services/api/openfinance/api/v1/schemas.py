from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from openfinance.application.imports import ImportPreview, ImportResult
from openfinance.application.savings import BudgetView, GoalView
from openfinance.domain.categories import Category, merchant_label
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
    category_id: UUID | None
    merchant: str = Field(description="Comercio normalizado y legible, p. ej. «Mercadona»")
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
            category_id=t.category_id,
            merchant=merchant_label(t.merchant),
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
    category_id: UUID | None = Field(description="Categoría propuesta por una regla aprendida")
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
                    category_id=r.category_id,
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


COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"


class CategoryOut(BaseModel):
    id: UUID
    name: str
    icon: str
    color: str
    hidden: bool
    slug: str | None

    @classmethod
    def of(cls, c: Category) -> CategoryOut:
        return cls(id=c.id, name=c.name, icon=c.icon, color=c.color, hidden=c.hidden, slug=c.slug)


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    icon: str = Field(default="🏷️", min_length=1, max_length=8)
    color: str = Field(default="#64748b", pattern=COLOR_PATTERN)


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    icon: str | None = Field(default=None, min_length=1, max_length=8)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    hidden: bool | None = None


class CategorizeIn(BaseModel):
    category_id: UUID | None
    learn: bool = Field(
        default=True,
        description="Guardar la regla «comercio → categoría» y aplicarla a los gastos sin ella",
    )


class RuleOut(BaseModel):
    merchant: str
    category_id: UUID


class CategorizeOut(BaseModel):
    transaction: TransactionOut
    rule: RuleOut | None
    also_categorized: int


class CountOut(BaseModel):
    count: int


class MemberAmountOut(BaseModel):
    member_id: UUID
    amount: MoneyOut


class CategoryAmountOut(BaseModel):
    category_id: UUID | None = Field(description="None = sin categoría")
    amount: MoneyOut
    average: MoneyOut | None = Field(description="Media de los meses completos anteriores")
    reference: MoneyOut | None = Field(
        description="La media o, en el mes en curso, la media hasta el mismo día"
    )
    change: MoneyOut | None = Field(description="amount - reference")


class MonthOverviewOut(BaseModel):
    month: str
    has_data: bool
    spent: MoneyOut
    previous_spent: MoneyOut | None
    is_partial: bool = Field(description="Mes en curso: los datos llegan hasta days_elapsed")
    days_elapsed: int
    previous_spent_to_date: MoneyOut | None = Field(
        description="Gasto del mes anterior hasta el mismo día (para comparar el mes en curso)"
    )
    average_spent: MoneyOut | None = Field(
        description="Media de gasto de los meses anteriores con datos (hasta 12)"
    )
    inflow: MoneyOut
    income: MoneyOut
    saved: MoneyOut
    saved_to_savings: MoneyOut
    saving_rate: int | None = Field(description="% de lo que entra que se ahorra")
    contributions: list[MemberAmountOut]
    contributed: MoneyOut = Field(
        description="Lo aportado a la conjunta desde estas cuentas (vista «mío»); no es gasto"
    )
    categories: list[CategoryAmountOut]
    changes: list[CategoryAmountOut] = Field(
        description="Las categorías que más cambian frente a su referencia (máx. 4)"
    )
    currency: str
    daily: list[str] = Field(description="Gasto acumulado al final de cada día (decimal exacto)")
    previous_daily: list[str]


class MonthAmountOut(BaseModel):
    month: str
    amount: MoneyOut
    has_data: bool


class MerchantOut(BaseModel):
    merchant: str
    amount: MoneyOut
    count: int


class CategoryDetailOut(BaseModel):
    category_id: UUID | None
    month: str
    months: list[MonthAmountOut]
    average: MoneyOut | None
    merchants: list[MerchantOut] = Field(description="Comercios principales de los últimos 3 meses")


class TrendCategoryOut(BaseModel):
    category_id: UUID | None
    amount: MoneyOut


class TrendMonthOut(BaseModel):
    month: str
    has_data: bool
    is_partial: bool = Field(
        description="Mes en curso: cuenta en los totales, no en las medias ni en el mejor o peor"
    )
    spent: MoneyOut
    inflow: MoneyOut
    saved: MoneyOut
    categories: list[TrendCategoryOut]


class MonthSavedOut(BaseModel):
    month: str
    saved: MoneyOut


class TrendsOut(BaseModel):
    months: list[TrendMonthOut]
    total_saved: MoneyOut
    total_inflow: MoneyOut
    total_spent: MoneyOut
    average_spent: MoneyOut | None
    average_saved: MoneyOut | None
    saving_rate: int | None
    best: MonthSavedOut | None
    worst: MonthSavedOut | None


AMOUNT_PATTERN = r"^\d{1,9}([.,]\d{1,2})?$"


class BudgetIn(BaseModel):
    amount: str = Field(pattern=AMOUNT_PATTERN, examples=["550", "550.00"])


class BudgetOut(BaseModel):
    category_id: UUID
    amount: MoneyOut
    spent: MoneyOut
    percent: int
    status: str = Field(description="ok, warning (≥ 85 %) u over (> 100 %)")

    @classmethod
    def of(cls, v: BudgetView) -> BudgetOut:
        return cls(
            category_id=v.budget.category_id,
            amount=MoneyOut.of(v.budget.amount),
            spent=MoneyOut.of(v.spent),
            percent=v.percent,
            status=v.status.value,
        )


class BudgetsOut(BaseModel):
    month: str
    items: list[BudgetOut]
    total_amount: MoneyOut | None
    total_spent: MoneyOut | None


MONTH_PATTERN = r"^(19|2\d)\d{2}-(0[1-9]|1[0-2])$"


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    icon: str = Field(default="🎯", min_length=1, max_length=8)
    target: str = Field(pattern=AMOUNT_PATTERN)
    monthly: str = Field(default="0", pattern=AMOUNT_PATTERN)
    saved: str = Field(default="0", pattern=AMOUNT_PATTERN)
    deadline: str | None = Field(default=None, pattern=MONTH_PATTERN)
    account_id: UUID | None = None


class GoalPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    icon: str | None = Field(default=None, min_length=1, max_length=8)
    target: str | None = Field(default=None, pattern=AMOUNT_PATTERN)
    monthly: str | None = Field(default=None, pattern=AMOUNT_PATTERN)
    saved: str | None = Field(default=None, pattern=AMOUNT_PATTERN)
    deadline: str | None = Field(
        default=None, pattern=r"^$|" + MONTH_PATTERN, description="AAAA-MM; vacío para quitarla"
    )
    account_id: UUID | None = None
    clear_account: bool = False


class GoalOut(BaseModel):
    id: UUID
    name: str
    icon: str
    target: MoneyOut
    monthly: MoneyOut
    saved: MoneyOut = Field(description="Lo ahorrado (saldo de la hucha si está vinculada)")
    deadline: str | None
    account_id: UUID | None
    remaining: MoneyOut
    progress: int
    months_to_go: int | None
    eta: str | None
    needed_monthly: MoneyOut | None
    on_track: bool | None

    @classmethod
    def of(cls, v: GoalView) -> GoalOut:
        g, p = v.goal, v.projection
        return cls(
            id=g.id,
            name=g.name,
            icon=g.icon,
            target=MoneyOut.of(g.target),
            monthly=MoneyOut.of(g.monthly),
            saved=MoneyOut.of(p.saved),
            deadline=str(g.deadline) if g.deadline else None,
            account_id=g.account_id,
            remaining=MoneyOut.of(p.remaining),
            progress=p.progress,
            months_to_go=p.months_to_go,
            eta=str(p.eta) if p.eta else None,
            needed_monthly=MoneyOut.of(p.needed_monthly) if p.needed_monthly else None,
            on_track=p.on_track,
        )


class PriceChangeOut(BaseModel):
    month: str
    before: MoneyOut
    after: MoneyOut


class RecurringOut(BaseModel):
    merchant: str
    category_id: UUID | None
    amount: MoneyOut
    first_amount: MoneyOut
    last_date: date
    months: int
    changes: list[PriceChangeOut]


class IdeaOut(BaseModel):
    id: str
    icon: str
    title: str
    detail: str
    yearly_saving: MoneyOut
    evidence: str
    assumption: str | None


class CategoryAverageOut(BaseModel):
    category_id: UUID | None
    average: MoneyOut


class SavingsOverviewOut(BaseModel):
    month: str = Field(description="Mes en curso según el servidor")
    months: list[str] = Field(description="Meses completos usados para las medias")
    average_saved: MoneyOut | None
    averages: list[CategoryAverageOut]
    recurring: list[RecurringOut]
    recurring_total: MoneyOut
    ideas: list[IdeaOut]
    goals: list[GoalOut]
