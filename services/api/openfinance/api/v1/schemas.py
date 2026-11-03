from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from openfinance.application.allowance import AllowanceView
from openfinance.application.allowance import Status as AllowanceStatus
from openfinance.application.decorate import Decor
from openfinance.application.imports import ImportPreview, ImportResult
from openfinance.application.savings import BudgetView, GoalView
from openfinance.domain.alerts import Alert
from openfinance.domain.allowance import Horizon as AllowanceHorizon
from openfinance.domain.attachments import Attachment
from openfinance.domain.automation import AutomationRule, Phase
from openfinance.domain.bank import BankConnection
from openfinance.domain.categories import Category, merchant_label
from openfinance.domain.csv_profile import CsvProfile
from openfinance.domain.forecast import BalancePoint, Forecast
from openfinance.domain.identity import User
from openfinance.domain.imports import PatternDirection
from openfinance.domain.ledger import (
    Account,
    AccountKind,
    AccountType,
    Institution,
    Transaction,
    TransactionKind,
)
from openfinance.domain.reconciliation import Reconciliation
from openfinance.domain.savings import BudgetMode, GoalContribution
from openfinance.domain.schedule import Frequency, Occurrence, OccurrenceStatus, ScheduledPayment
from openfinance.domain.shared import Money
from openfinance.domain.templates import TransactionTemplate
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
    type: AccountType
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
            type=account.type,
            owner_id=account.owner_id,
            opening_balance=MoneyOut.of(account.opening_balance),
            balance=MoneyOut.of(balance),
        )


class SplitPartOut(BaseModel):
    amount: MoneyOut
    category_id: UUID


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
    note: str = Field(description="Nota de quien corrigió el movimiento")
    tags: list[str] = Field(description="Etiquetas del movimiento")
    parts: list[SplitPartOut] = Field(
        description="Partes con categoría si el gasto está dividido (suman su importe)"
    )
    reviewed: bool = Field(description="Revisado contra el banco")
    attachment_count: int = Field(description="Tickets o facturas adjuntos")
    transfer_peer_id: UUID | None = Field(
        description="El otro lado del traspaso, si está enlazado y tú también lo ves"
    )

    @classmethod
    def of(cls, t: Transaction, decor: Decor | None = None) -> TransactionOut:
        """``decor``: nombre del comercio, etiquetas y partes (OF-1001 a OF-1003)."""
        d = decor or Decor()
        return cls(
            id=t.id,
            account_id=t.account_id,
            booked_at=t.booked_at,
            value_date=t.value_date,
            description=t.description,
            amount=MoneyOut.of(t.amount),
            kind=t.kind,
            category_id=t.category_id,
            merchant=d.names.get(t.merchant) or merchant_label(t.merchant),
            member_id=t.member_id,
            source=t.source,
            note=t.note,
            tags=list(d.tags.get(t.id, ())),
            reviewed=t.reviewed,
            attachment_count=d.attachments.get(t.id, 0),
            transfer_peer_id=d.peers.get(t.id),
            parts=[
                SplitPartOut(amount=MoneyOut.of(p.amount), category_id=p.category_id)
                for p in d.splits.get(t.id, [])
            ],
        )


class TransactionPageOut(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None = Field(
        description="Pásalo como `cursor` para pedir la página siguiente; null en la última"
    )
    count: int = Field(description="Movimientos que cumplen el filtro en total")
    total: MoneyOut = Field(
        description="Suma con signo de los que cumplen el filtro y van en la moneda del hogar"
    )
    other_currencies: list[str] = Field(
        description="Monedas de movimientos del filtro que no entran en `total`"
    )


class PreviewRowOut(BaseModel):
    line: int
    booked_at: datetime
    description: str
    amount: MoneyOut
    kind: TransactionKind
    member_id: UUID | None
    category_id: UUID | None = Field(description="Categoría propuesta por una regla")
    tags: list[str] = Field(description="Etiquetas que pondrán las reglas")
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
    members_without_recharge: list[UUID] = Field(
        description="Quién no tiene guardada su tarjeta de recarga: sus recargas entrarían como "
        "ingreso. La web pide confirmación antes de importar."
    )

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
                    kind=r.kind,
                    member_id=r.member_id,
                    category_id=r.category_id,
                    tags=list(r.tags),
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
            members_without_recharge=list(p.members_without_recharge),
        )


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class RevokedOut(BaseModel):
    revoked: int = Field(description="Sesiones cerradas en otros navegadores")


class PatternOut(BaseModel):
    pattern: str
    direction: PatternDirection


class PatternIn(BaseModel):
    pattern: str = Field(min_length=3, max_length=60, examples=["*1234"])
    direction: PatternDirection = PatternDirection.INFLOW


class ImportListItemOut(BaseModel):
    id: UUID
    account_id: UUID
    filename: str
    created_by: UUID
    committed_at: datetime | None
    status: Literal["committed", "undone"]
    created: int
    duplicates: int
    skipped: int
    can_undo: bool = Field(description="Solo la última importación confirmada de cada cuenta")


class UndoImportOut(BaseModel):
    voided: int = Field(description="Movimientos anulados")
    operation_id: UUID | None
    kept_reviewed: int = Field(
        default=0, description="Movimientos revisados que se han dejado como estaban"
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
    """Corrección de un movimiento: solo cambia lo que se envía (OF-701)."""

    category_id: UUID | None = Field(default=None, description="null = quitar la categoría")
    kind: TransactionKind | None = None
    member_id: UUID | None = Field(default=None, description="Quién aporta, en una aportación")
    note: str | None = Field(default=None, max_length=2000)
    learn: bool = Field(
        default=True,
        description="Guardar la regla «comercio → categoría» y aplicarla a los gastos sin ella",
    )


class RuleOut(BaseModel):
    merchant: str
    category_id: UUID


class RuleViewOut(BaseModel):
    key: str = Field(description="Comercio normalizado, para borrar la regla")
    merchant: str = Field(description="Comercio legible")
    category_id: UUID
    scope: Literal["household", "personal"] = Field(
        description="personal = aprendida en tu cuenta personal; solo la ves tú"
    )
    matches: int = Field(description="Movimientos con esa categoría que coinciden con la regla")


class CategorizeOut(BaseModel):
    transaction: TransactionOut
    rule: RuleOut | None
    also_categorized: int
    operation_id: UUID | None = Field(description="Para deshacer la corrección (ADR-0017)")


AMOUNT_PATTERN = r"^\d{1,9}([.,]\d{1,2})?$"
AMOUNT_PATTERN_SIGNED = r"^-?\d{1,9}([.,]\d{1,2})?$"


class BulkCategorizeIn(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=500)
    category_id: UUID | None


class BulkCategorizeOut(BaseModel):
    updated: int
    operation_id: UUID | None


class ManualTransactionIn(BaseModel):
    """Un movimiento que no viene de ningún extracto, p. ej. un pago en efectivo (OF-705)."""

    account_id: UUID
    booked_on: date
    description: str = Field(min_length=1, max_length=200)
    amount: str = Field(pattern=AMOUNT_PATTERN, description="Positivo; un gasto resta")
    kind: TransactionKind = TransactionKind.EXPENSE
    category_id: UUID | None = None
    note: str = Field(default="", max_length=2000)


class ManualTransactionOut(BaseModel):
    transaction: TransactionOut
    operation_id: UUID | None


class AlertOut(BaseModel):
    kind: Literal[
        "late_payment", "low_balance", "budget_over", "duplicate", "price_rise", "fee", "consent"
    ]
    key: str = Field(description="Estable entre consultas; sirve para descartarlo")
    severity: Literal["info", "warning", "critical"]
    title: str
    detail: str
    on: date
    amount: MoneyOut | None
    account_id: UUID | None

    @classmethod
    def of(cls, a: Alert) -> AlertOut:
        return cls(
            kind=a.kind.value,
            key=a.key,
            severity=a.severity.value,
            title=a.title,
            detail=a.detail,
            on=a.on,
            amount=MoneyOut.of(a.amount) if a.amount else None,
            account_id=UUID(a.account_id) if a.account_id else None,
        )


class AlertDismissIn(BaseModel):
    key: str = Field(min_length=1, max_length=160)


class OperationRefOut(BaseModel):
    operation_id: UUID | None


class ChangeOut(BaseModel):
    entity: str
    field: str
    before: str | bool | None
    after: str | bool | None


class OperationOut(BaseModel):
    id: UUID
    actor_id: UUID
    created_at: datetime
    action: str
    summary: str
    undone: bool
    changes: list[ChangeOut] = Field(description="En el historial de un movimiento, solo los suyos")


class RevertOut(BaseModel):
    operation: OperationOut
    applied: int
    kept: int = Field(description="Cambios respetados porque alguien los hizo después")
    kept_by: list[UUID]


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


class PendingChargeOut(BaseModel):
    merchant: str
    category_id: UUID | None
    amount: MoneyOut
    expected_day: int = Field(description="Día del mes en que suele cobrarse")
    late: bool = Field(description="Ya tocaba cobrarla este mes y no ha llegado; no se suma")


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
    forecast: MoneyOut | None = Field(
        description="Gasto con el que cerraría el mes en curso; null si hay pocos días de datos"
    )
    pending_charges: list[PendingChargeOut] = Field(
        description="Cuotas habituales que este mes aún no han llegado (solo el mes en curso)"
    )


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


class BudgetIn(BaseModel):
    amount: str = Field(pattern=AMOUNT_PATTERN, examples=["550", "550.00"])
    mode: BudgetMode = Field(
        default=BudgetMode.LIMIT,
        description="limit: un tope por mes. envelope: lo que sobra o falta pasa al mes siguiente",
    )
    started: str | None = Field(
        default=None,
        pattern=r"^(19|2\d)\d{2}-(0[1-9]|1[0-2])$",
        description="En un sobre, desde qué mes se arrastra (por defecto, el actual)",
    )


class BudgetMonthIn(BaseModel):
    amount: str = Field(pattern=AMOUNT_PATTERN, examples=["900"])


class BudgetOut(BaseModel):
    category_id: UUID
    amount: MoneyOut
    spent: MoneyOut
    percent: int
    status: str = Field(
        description="ok, warning (≥ 85 % del margen que dejan las cuotas fijas) u over (> 100 %)"
    )
    fixed: MoneyOut = Field(
        description="Cuotas fijas de la categoría este mes, cobradas y por cobrar (OF-802)"
    )
    mode: BudgetMode
    base_amount: MoneyOut = Field(description="El importe de cualquier mes sin importe propio")
    has_override: bool = Field(description="Ese mes tiene un importe propio")
    carried: MoneyOut = Field(description="Lo que arrastra un sobre de los meses anteriores")
    available: MoneyOut = Field(description="Lo asignado más lo arrastrado, menos lo gastado")
    started: str | None = Field(description="Mes desde el que un sobre arrastra (AAAA-MM)")

    @classmethod
    def of(cls, v: BudgetView) -> BudgetOut:
        return cls(
            fixed=MoneyOut.of(v.fixed),
            category_id=v.budget.category_id,
            amount=MoneyOut.of(v.allocated),
            mode=v.budget.mode,
            base_amount=MoneyOut.of(v.budget.amount),
            has_override=v.has_override,
            carried=MoneyOut.of(v.carried),
            available=MoneyOut.of(v.available),
            started=str(v.budget.started) if v.budget.started else None,
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
    priority: int = Field(default=50, ge=1, le=99, description="Cuanto menor, antes")


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
    priority: int | None = Field(default=None, ge=1, le=99)


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
    priority: int

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
            priority=g.priority,
        )


class ContributionIn(BaseModel):
    amount: str = Field(
        pattern=AMOUNT_PATTERN_SIGNED, description="Positivo aporta; negativo retira"
    )
    made_on: date | None = Field(default=None, description="Por defecto, hoy")
    note: str = Field(default="", max_length=200)


class ContributionOut(BaseModel):
    id: UUID
    goal_id: UUID
    made_on: date
    amount: MoneyOut
    note: str

    @classmethod
    def of(cls, c: GoalContribution) -> ContributionOut:
        return cls(
            id=c.id, goal_id=c.goal_id, made_on=c.made_on, amount=MoneyOut.of(c.amount), note=c.note
        )


class ContributionChangeOut(BaseModel):
    contribution: ContributionOut
    operation_id: UUID | None


class ShareOut(BaseModel):
    goal_id: UUID
    name: str
    amount: MoneyOut = Field(description="Lo que se sugiere aportar a este objetivo")
    remaining: MoneyOut


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
    dismissed: bool = Field(description="El hogar la ha descartado; se puede recuperar (OF-806)")


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


class MerchantGroupOut(BaseModel):
    id: UUID | None = Field(description="Nulo mientras nadie le haya puesto nombre propio")
    name: str
    keys: list[str] = Field(description="Variantes del banco que aparecen en tus cuentas")
    count: int
    total: MoneyOut = Field(description="Suma de sus movimientos; los gastos suman en negativo")


class MerchantRenameIn(BaseModel):
    key: str = Field(min_length=1, max_length=100, description="Cualquier variante del comercio")
    name: str = Field(min_length=1, max_length=60)


class MerchantMergeIn(BaseModel):
    target_key: str = Field(min_length=1, max_length=100, description="Comercio que se queda")
    source_key: str = Field(min_length=1, max_length=100, description="Comercio que se absorbe")


class MerchantChangeOut(BaseModel):
    merchant: MerchantGroupOut
    reclassified: int = Field(description="Gastos sin categoría que han tomado la del destino")
    operation_id: UUID | None


class TagOut(BaseModel):
    tag: str
    count: int = Field(description="Movimientos que la llevan, entre los que ves")


class TagsIn(BaseModel):
    tags: list[str] = Field(max_length=10, description="Sustituye las etiquetas del movimiento")


class TagsOut(BaseModel):
    transaction: TransactionOut
    operation_id: UUID | None


class SplitPartIn(BaseModel):
    amount: str = Field(
        pattern=AMOUNT_PATTERN_SIGNED, description="Con el signo del gasto, p. ej. «-60.00»"
    )
    category_id: UUID


class SplitIn(BaseModel):
    parts: list[SplitPartIn] = Field(min_length=2, max_length=10)


class SplitOut(BaseModel):
    transaction: TransactionOut
    operation_id: UUID | None


class LinkIn(BaseModel):
    peer_id: UUID = Field(description="El otro lado del traspaso")


class LinkOut(BaseModel):
    transaction: TransactionOut
    peer: TransactionOut
    operation_id: UUID | None


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AccountType = Field(
        description="Efectivo, tarjeta, préstamo o inversión; las de banco, desde el servidor"
    )
    shared: bool = Field(description="De todo el hogar (true) o solo tuya (false)")
    currency: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z]{3}$",
        description="Moneda de la cuenta; por defecto, la del hogar",
    )
    opening_balance: str = Field(
        default="0",
        pattern=AMOUNT_PATTERN_SIGNED,
        description="Saldo de partida. Una deuda (tarjeta o préstamo) va en negativo",
    )


class ReviewIn(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=500)
    reviewed: bool = Field(description="true = revisados; false = quitar la marca")


class ReviewOut(BaseModel):
    changed: int = Field(description="Movimientos que han cambiado de estado")
    operation_id: UUID | None


class ReconcileIn(BaseModel):
    as_of: date = Field(description="Día del saldo que da el banco")
    bank_balance: str = Field(pattern=AMOUNT_PATTERN_SIGNED, description="Saldo según el banco")


class ReconciliationOut(BaseModel):
    id: UUID
    account_id: UUID
    as_of: date
    bank_balance: MoneyOut
    computed_balance: MoneyOut
    difference: MoneyOut = Field(description="Positivo: falta en OpenFinance; negativo: sobra")
    matches: bool
    created_by: UUID
    created_at: datetime

    @classmethod
    def of(cls, r: Reconciliation) -> ReconciliationOut:
        return cls(
            id=r.id,
            account_id=r.account_id,
            as_of=r.as_of,
            bank_balance=MoneyOut.of(r.bank_balance),
            computed_balance=MoneyOut.of(r.computed_balance),
            difference=MoneyOut.of(r.difference),
            matches=r.matches,
            created_by=r.created_by,
            created_at=r.created_at,
        )


class AttachmentOut(BaseModel):
    id: UUID
    transaction_id: UUID
    filename: str
    content_type: str
    size: int
    created_by: UUID
    created_at: datetime

    @classmethod
    def of(cls, a: Attachment) -> AttachmentOut:
        return cls(
            id=a.id,
            transaction_id=a.transaction_id,
            filename=a.filename,
            content_type=a.content_type,
            size=a.size,
            created_by=a.created_by,
            created_at=a.created_at,
        )


class AttachmentAddedOut(BaseModel):
    attachment: AttachmentOut
    operation_id: UUID | None


class RateOut(BaseModel):
    currency: str
    on: date
    rate: str = Field(description="Unidades de la moneda del hogar por 1 de esta moneda")
    source: str


class RateIn(BaseModel):
    currency: str = Field(pattern=r"^[A-Za-z]{3}$", description="Código ISO, p. ej. USD")
    on: date
    rate: str = Field(pattern=r"^\d{1,9}([.,]\d{1,8})?$", description="Mayor que cero")


class RateSetOut(BaseModel):
    rate: RateOut
    operation_id: UUID | None


class MissingRateOut(BaseModel):
    currency: str
    count: int = Field(description="Movimientos que no entran en los informes por falta de tipo")
    first: date = Field(description="Fecha del más antiguo: el tipo ha de ser de ese día o antes")


class ConditionIn(BaseModel):
    field: Literal["description", "merchant", "amount", "direction", "account", "bank_type"]
    op: str = Field(default="equals", description="contains, starts_with, equals, between, is, in")
    value: str | list[str]


class ActionIn(BaseModel):
    type: Literal["set_category", "set_kind", "add_tags", "set_note", "set_merchant"]
    value: str | list[str]


class AutomationRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    personal: bool = Field(default=False, description="Solo tuya (si no, de todo el hogar)")
    phase: Phase = Phase.NORMAL
    priority: int | None = Field(default=None, ge=0, le=100000, description="Menor = antes")
    enabled: bool = True
    conditions: list[ConditionIn] = Field(min_length=1, max_length=8)
    actions: list[ActionIn] = Field(min_length=1, max_length=6)


class AutomationRuleOut(BaseModel):
    id: UUID
    name: str
    personal: bool
    phase: Phase
    priority: int
    enabled: bool
    conditions: list[ConditionIn]
    actions: list[ActionIn]

    @classmethod
    def of(cls, rule: AutomationRule) -> AutomationRuleOut:
        return cls(
            id=rule.id,
            name=rule.name,
            personal=rule.scope != "",
            phase=rule.phase,
            priority=rule.priority,
            enabled=rule.enabled,
            conditions=[ConditionIn(**c.as_json()) for c in rule.conditions],
            actions=[ActionIn(**a.as_json()) for a in rule.actions],
        )


class AutomationRuleChangeOut(BaseModel):
    rule: AutomationRuleOut
    operation_id: UUID | None


class ProposedChangeOut(BaseModel):
    field: str
    before: str | bool | None
    after: str | bool | None


class ProposedOut(BaseModel):
    transaction: TransactionOut
    changes: list[ProposedChangeOut]


class RulePreviewOut(BaseModel):
    count: int = Field(description="Movimientos que cambiaría, de los que ves")
    items: list[ProposedOut] = Field(description="Los primeros 100")


class RuleApplyOut(BaseModel):
    changed: int
    operation_id: UUID | None


class CsvProfileConfig(BaseModel):
    delimiter: str = Field(
        default=",", description="Coma, punto y coma, tabulador o barra vertical"
    )
    encoding: str = Field(default="utf-8", description="utf-8, cp1252 o latin-1")
    skip_rows: int = Field(default=0, ge=0, le=50, description="Líneas antes de la cabecera")
    has_header: bool = True
    date_column: int = Field(ge=0, le=29)
    date_format: str
    description_columns: list[int] = Field(min_length=1, max_length=4)
    amount_mode: Literal["single", "debit_credit"] = "single"
    amount_column: int | None = Field(default=None, ge=0, le=29)
    debit_column: int | None = Field(default=None, ge=0, le=29)
    credit_column: int | None = Field(default=None, ge=0, le=29)
    decimal_separator: Literal[",", "."] = ","
    invert_sign: bool = False
    balance_column: int | None = Field(default=None, ge=0, le=29)


class CsvProfileIn(CsvProfileConfig):
    name: str = Field(min_length=1, max_length=80)


class CsvProfileOut(CsvProfileConfig):
    id: UUID
    name: str

    @classmethod
    def of(cls, p: CsvProfile) -> CsvProfileOut:
        return cls(id=p.id, name=p.name, **p.config())


class CsvProfileChangeOut(BaseModel):
    profile: CsvProfileOut
    operation_id: UUID | None


class CsvSampleOut(BaseModel):
    delimiter: str
    encoding: str
    rows: list[list[str]] = Field(description="Las primeras filas, tal cual, para elegir columnas")


class CsvTestRowOut(BaseModel):
    line: int
    booked_at: datetime
    description: str
    amount: MoneyOut
    balance: MoneyOut | None


class CsvTestOut(BaseModel):
    rows: list[CsvTestRowOut]
    total: int = Field(description="Filas que se leen bien en todo el archivo")
    skipped: list[SkippedRowOut]
    skipped_total: int


# --- OF-1201 · Pagos programados ------------------------------------------------------------


class ScheduledPaymentIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    amount: str = Field(
        max_length=20, examples=["-900.00"], description="Con signo: negativo es un pago"
    )
    account_id: UUID
    frequency: Frequency
    interval: int = Field(default=1, ge=1, le=60)
    first_due: date
    ends_on: date | None = None
    category_id: UUID | None = None
    merchant: str = Field(default="", max_length=120)
    variable: bool = False
    active: bool = True


class ScheduledPaymentOut(BaseModel):
    id: UUID
    name: str
    amount: MoneyOut
    account_id: UUID
    frequency: Frequency
    interval: int
    first_due: date
    ends_on: date | None
    category_id: UUID | None
    merchant: str
    variable: bool
    active: bool

    @classmethod
    def of(cls, p: ScheduledPayment) -> ScheduledPaymentOut:
        return cls(
            id=p.id,
            name=p.name,
            amount=MoneyOut.of(p.amount),
            account_id=p.account_id,
            frequency=p.frequency,
            interval=p.interval,
            first_due=p.first_due,
            ends_on=p.ends_on,
            category_id=p.category_id,
            merchant=p.merchant,
            variable=p.variable,
            active=p.active,
        )


class OccurrenceOut(BaseModel):
    due: date
    amount: MoneyOut
    status: OccurrenceStatus
    transaction_id: UUID | None


class ScheduleItemOut(BaseModel):
    payment: ScheduledPaymentOut
    occurrences: list[OccurrenceOut]


class ScheduledPaymentChangeOut(BaseModel):
    payment: ScheduledPaymentOut
    operation_id: UUID | None


# --- OF-1202 · Previsión de saldo -----------------------------------------------------------


class ForecastPointOut(BaseModel):
    day: date
    balance: MoneyOut


class ForecastOut(BaseModel):
    account_id: UUID | None = Field(description="Vacío en el total de una moneda")
    name: str | None
    currency: str
    start: MoneyOut
    end: MoneyOut
    lowest: ForecastPointOut
    first_negative: date | None
    points: list[ForecastPointOut] = Field(description="Hoy y cada día en que el saldo cambia")

    @classmethod
    def of(cls, f: Forecast, currency: str, account: Account | None = None) -> ForecastOut:
        def point(p: BalancePoint) -> ForecastPointOut:
            return ForecastPointOut(day=p.day, balance=MoneyOut.of(p.balance))

        return cls(
            account_id=account.id if account else None,
            name=account.name if account else None,
            currency=currency,
            start=MoneyOut.of(f.start),
            end=MoneyOut.of(f.end),
            lowest=point(f.lowest),
            first_negative=f.first_negative,
            points=[point(p) for p in f.points],
        )


class ForecastViewOut(BaseModel):
    until: date
    accounts: list[ForecastOut]
    totals: list[ForecastOut]


# --- OF-1204 · Plantillas de movimientos ----------------------------------------------------


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: TransactionKind = TransactionKind.EXPENSE
    amount: str = Field(pattern=AMOUNT_PATTERN, description="Positivo; el tipo da el signo")
    description: str = Field(min_length=1, max_length=200)
    account_id: UUID
    personal: bool = Field(default=False, description="Solo la ve quien la crea")
    category_id: UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=2000)


class TemplateOut(BaseModel):
    id: UUID
    name: str
    kind: TransactionKind
    amount: MoneyOut
    description: str
    account_id: UUID
    personal: bool
    category_id: UUID | None
    tags: list[str]
    note: str

    @classmethod
    def of(cls, t: TransactionTemplate, currency: str) -> TemplateOut:
        return cls(
            id=t.id,
            name=t.name,
            kind=t.kind,
            amount=MoneyOut(amount=str(t.amount), currency=currency),
            description=t.description,
            account_id=t.account_id,
            personal=t.personal,
            category_id=t.category_id,
            tags=list(t.tags),
            note=t.note,
        )


class TemplateChangeOut(BaseModel):
    template: TemplateOut
    operation_id: UUID | None


class TemplateUseIn(BaseModel):
    booked_on: date | None = Field(default=None, description="Por defecto, hoy")


# --- OF-1205 · «Hoy podéis gastar» ----------------------------------------------------------


class AllowanceItemOut(BaseModel):
    name: str
    due: date
    amount: MoneyOut


class EnvelopeLeftOut(BaseModel):
    category_id: UUID
    available: MoneyOut
    status: str


class AllowanceOut(BaseModel):
    status: AllowanceStatus
    balance: MoneyOut | None
    committed: MoneyOut | None = Field(description="Lo que está por pagar hasta el horizonte")
    available: MoneyOut | None = Field(
        description="Saldo menos lo comprometido; puede ser negativo"
    )
    per_day: MoneyOut | None = Field(description="Lo que se puede gastar cada día")
    days: int | None
    until: date | None
    horizon: AllowanceHorizon | None
    short: bool = Field(description="Lo comprometido es más que el saldo")
    pending: list[AllowanceItemOut]
    next_income: AllowanceItemOut | None
    envelopes: list[EnvelopeLeftOut]

    @classmethod
    def of(cls, v: AllowanceView) -> AllowanceOut:
        a = v.allowance
        envelopes = [
            EnvelopeLeftOut(
                category_id=e.budget.category_id,
                available=MoneyOut.of(e.available),
                status=e.status.value,
            )
            for e in v.envelopes
        ]
        if a is None:
            return cls(
                status=v.status,
                balance=None,
                committed=None,
                available=None,
                per_day=None,
                days=None,
                until=None,
                horizon=None,
                short=False,
                pending=[],
                next_income=None,
                envelopes=envelopes,
            )

        def item(o: Occurrence) -> AllowanceItemOut:
            return AllowanceItemOut(
                name=v.names.get(o.payment_id, "Pago"), due=o.due, amount=MoneyOut.of(o.amount)
            )

        return cls(
            status=v.status,
            balance=MoneyOut.of(a.balance),
            committed=MoneyOut.of(a.committed),
            available=MoneyOut.of(a.available),
            per_day=MoneyOut.of(a.per_day),
            days=a.days,
            until=a.until,
            horizon=a.horizon,
            short=a.short,
            pending=[item(o) for o in a.pending],
            next_income=item(a.next_income) if a.next_income else None,
            envelopes=envelopes,
        )


class NotificationPrefsIn(BaseModel):
    kinds: list[
        Literal[
            "late_payment",
            "low_balance",
            "budget_over",
            "duplicate",
            "price_rise",
            "fee",
            "consent",
        ]
    ] = Field(max_length=6)
    weekly: bool


class NotificationsOut(BaseModel):
    configured: bool = Field(description="Hay claves VAPID y el servidor puede enviar")
    public_key: str | None = Field(description="Clave pública VAPID para suscribirse")
    devices: int
    kinds: list[
        Literal[
            "late_payment",
            "low_balance",
            "budget_over",
            "duplicate",
            "price_rise",
            "fee",
            "consent",
        ]
    ]
    weekly: bool


class PushKeysIn(BaseModel):
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=500)
    keys: PushKeysIn


class PushEndpointIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=500)


class WeekCategoryOut(BaseModel):
    category_id: UUID | None
    amount: MoneyOut


class UpcomingPaymentOut(BaseModel):
    name: str
    due: date
    amount: MoneyOut


class WeeklySummaryOut(BaseModel):
    start: date
    end: date
    spent: MoneyOut
    previous: MoneyOut
    change_percent: int | None = Field(description="Respecto a la semana anterior; nulo sin base")
    top: list[WeekCategoryOut]
    upcoming: list[UpcomingPaymentOut]
    open_alerts: int


class BankLinkOut(BaseModel):
    remote_uid: str
    iban_tail: str = Field(description="Últimos cuatro caracteres del IBAN")
    name: str
    currency: str
    account_id: UUID | None = Field(description="Cuenta del hogar a la que alimenta, si se eligió")
    bank_balance: MoneyOut | None = Field(description="Último saldo que informó el banco")
    bank_balance_at: datetime | None
    balance_difference: MoneyOut | None = Field(
        description="Saldo del banco menos el calculado en OpenFinance al sincronizar"
    )


class BankConnectionOut(BaseModel):
    id: UUID
    aspsp: str
    country: str
    status: Literal["pending", "active", "expired", "revoked"]
    valid_until: datetime | None
    expires_soon: bool
    last_sync_at: datetime | None
    last_error: str
    links: list[BankLinkOut]

    @classmethod
    def of(cls, c: BankConnection, now: datetime) -> BankConnectionOut:
        return cls(
            id=c.id,
            aspsp=c.aspsp,
            country=c.country,
            status=c.status.value,
            valid_until=c.valid_until,
            expires_soon=c.expires_soon(now),
            last_sync_at=c.last_sync_at,
            last_error=c.last_error,
            links=[
                BankLinkOut(
                    remote_uid=link.remote_uid,
                    iban_tail=link.iban_tail,
                    name=link.name,
                    currency=link.currency,
                    account_id=link.account_id,
                    bank_balance=MoneyOut.of(link.bank_balance) if link.bank_balance else None,
                    bank_balance_at=link.bank_balance_at,
                    balance_difference=(
                        MoneyOut.of(link.balance_difference) if link.balance_difference else None
                    ),
                )
                for link in c.links
            ],
        )


class BankOut(BaseModel):
    configured: bool = Field(
        description="Hay aplicación del agregador y el servidor puede conectar"
    )
    connections: list[BankConnectionOut]


class BankStartIn(BaseModel):
    aspsp: str = Field(min_length=1, max_length=100, description="Nombre del banco en el agregador")
    country: str = Field(min_length=2, max_length=2, examples=["ES"])


class BankStartOut(BaseModel):
    connection_id: UUID
    url: str = Field(description="Dirección del banco donde la persona autoriza")


class BankCompleteIn(BaseModel):
    state: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=500)


class BankLinkIn(BaseModel):
    remote_uid: str = Field(min_length=1, max_length=200)
    account_id: UUID | None = Field(description="Cuenta del hogar; null desenlaza")


class BankRevokeOut(BaseModel):
    connection: BankConnectionOut
    closed_at_bank: bool


class BankSyncLinkOut(BaseModel):
    name: str
    created: int
    duplicates: int
    reconciled: int = Field(description="Conciliados con un movimiento ya anotado")
    skipped: int
    error: str


class BankSyncOut(BaseModel):
    connection: BankConnectionOut
    created: int = Field(description="Movimientos nuevos guardados en todas las cuentas")
    links: list[BankSyncLinkOut]
    skipped_reason: str = Field(description="Por qué no se intentó, si no se hizo")


class WorthPointOut(BaseModel):
    on: date
    assets: MoneyOut
    debts: MoneyOut = Field(description="Cuánto se debe, en positivo")
    net: MoneyOut
    excluded: int = Field(description="Cuentas que no entran por falta de tipo de cambio")


class AccountWorthOut(BaseModel):
    account_id: UUID
    name: str
    type: Literal["bank", "cash", "card", "loan", "investment"]
    balance: MoneyOut = Field(description="En la moneda de la cuenta")
    value: MoneyOut | None = Field(description="En la moneda del hogar; null si falta el tipo")


class TypeWorthOut(BaseModel):
    type: Literal["bank", "cash", "card", "loan", "investment"]
    net: MoneyOut


class NetWorthOut(BaseModel):
    currency: str
    today: WorthPointOut
    history: list[WorthPointOut] = Field(description="Fines de mes y hoy, del más antiguo al nuevo")
    accounts: list[AccountWorthOut]
    by_type: list[TypeWorthOut]
    missing_rates: list[str] = Field(description="Monedas sin tipo de cambio para alguna fecha")


class MonthFlowOut(BaseModel):
    month: str = Field(examples=["2026-10"])
    income: MoneyOut
    contributions: MoneyOut = Field(
        description="Neto: entra a la conjunta menos sale de una personal"
    )
    spending: MoneyOut = Field(description="Gasto neto de devoluciones, en positivo")
    savings: MoneyOut = Field(description="Movido al ahorro, neto de lo que se saca, en positivo")
    transfers: MoneyOut = Field(description="Traspasos entre cuentas propias, netos")
    change: MoneyOut = Field(description="Variación del saldo del mes")
    end_balance: MoneyOut
    is_partial: bool


class CashFlowOut(BaseModel):
    currency: str
    months: list[MonthFlowOut]
    accounts: int = Field(description="Cuentas líquidas que entran en las cifras")
    excluded_foreign: int = Field(
        description="Cuentas líquidas en otra moneda, fuera de las cifras"
    )
