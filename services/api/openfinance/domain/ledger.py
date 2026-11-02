"""Cuentas y movimientos del hogar."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from openfinance.domain.categories import CategoryId, merchant_key
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, TransactionId, UserId, WorkspaceId


class LedgerError(ValueError):
    pass


class Institution(StrEnum):
    REVOLUT = "revolut"
    BANKINTER = "bankinter"
    OTHER = "other"


class AccountKind(StrEnum):
    JOINT = "joint"
    """Cuenta conjunta de la casa: la ven todos los miembros."""
    PERSONAL = "personal"
    """Cuenta de una persona: solo la ve su titular."""
    SAVINGS = "savings"
    """Hucha o cuenta de ahorro del hogar: la ven todos los miembros."""


class AccountType(StrEnum):
    """Para qué sirve la cuenta (OF-1005). Es independiente de quién la ve (``AccountKind``).

    Todas son solo de seguimiento: OpenFinance no mueve ni contrata nada.
    """

    BANK = "bank"
    """Cuenta corriente o de ahorro de un banco (la de siempre)."""
    CASH = "cash"
    """Efectivo."""
    CARD = "card"
    """Tarjeta de crédito: el saldo negativo es lo que se debe. Sus compras son gasto."""
    LOAN = "loan"
    """Préstamo o hipoteca que ya existe: el saldo negativo es lo pendiente. No es gasto."""
    INVESTMENT = "investment"
    """Inversión: su valor se anota a mano o por movimientos. No es gasto."""

    @property
    def is_liability(self) -> bool:
        return self in (AccountType.CARD, AccountType.LOAN)

    @property
    def counts_in_reports(self) -> bool:
        """Si sus movimientos entran en gasto, presupuestos e informes del mes."""
        return self not in (AccountType.LOAN, AccountType.INVESTMENT)


MAX_NOTE = 2000


class TransactionKind(StrEnum):
    """Qué significa un movimiento para el hogar (ADR-0012)."""

    CONTRIBUTION = "contribution"
    """Aportación de una persona a la cuenta conjunta (entrada) o desde su cuenta (salida)."""
    EXPENSE = "expense"
    """Gasto. Un importe positivo es una devolución y resta gasto."""
    INCOME = "income"
    """Otros ingresos (intereses, Bizum recibidos…)."""
    SAVINGS_TRANSFER = "savings_transfer"
    """Traspaso a hucha o cuenta de ahorro. Es ahorro, no gasto."""
    INTERNAL_TRANSFER = "internal_transfer"
    """Movimiento entre cuentas propias que no es gasto ni ahorro."""


@dataclass(frozen=True, slots=True)
class Account:
    id: AccountId
    household_id: WorkspaceId
    name: str
    institution: Institution
    kind: AccountKind
    currency: Currency
    opening_balance: Money
    owner_id: UserId | None = None
    type: AccountType = AccountType.BANK

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise LedgerError("La cuenta necesita un nombre")
        if self.opening_balance.currency != self.currency:
            raise LedgerError("El saldo inicial debe estar en la moneda de la cuenta")
        if self.kind is AccountKind.PERSONAL and self.owner_id is None:
            raise LedgerError("Una cuenta personal necesita titular")
        if self.kind is not AccountKind.PERSONAL and self.owner_id is not None:
            raise LedgerError("Solo las cuentas personales tienen titular")

    def visible_to(self, user_id: UserId) -> bool:
        return self.kind is not AccountKind.PERSONAL or self.owner_id == user_id


def normalize_note(text: str) -> str:
    """Nota con saltos de línea: espacios sobrantes fuera, sin líneas vacías seguidas ni al
    principio o al final (OF-1002)."""
    lines = [" ".join(line.split()) for line in text.replace("\r\n", "\n").split("\n")]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip("\n")


@dataclass(frozen=True, slots=True)
class Transaction:
    id: TransactionId
    household_id: WorkspaceId
    account_id: AccountId
    booked_at: datetime
    """Fecha y hora del movimiento según el banco (hora local del extracto)."""
    value_date: date
    description: str
    amount: Money
    kind: TransactionKind
    category_id: CategoryId | None = None
    member_id: UserId | None = None
    """Quién aporta, en las aportaciones."""
    bank_type: str = ""
    source: str = "manual"
    """Procedencia: ``manual`` o ``import:<archivo>``."""
    fingerprint: str | None = None
    import_id: UUID | None = None
    """Importación de la que procede, si viene de un extracto."""
    merchant: str = ""
    """Comercio normalizado; se calcula a partir del concepto si no se indica."""
    note: str = ""
    """Nota de quien corrige el movimiento (OF-701)."""
    voided: bool = False
    """Anulado (borrado o importación deshecha): no cuenta en nada, pero no se borra (ADR-0017)."""
    reviewed: bool = False
    """Revisado contra el banco (OF-1006): deshacer una importación o aplicar reglas no lo toca."""

    def __post_init__(self) -> None:
        if self.kind is TransactionKind.CONTRIBUTION and self.member_id is None:
            raise LedgerError("Una aportación necesita indicar de quién es")
        if self.kind is not TransactionKind.CONTRIBUTION and self.member_id is not None:
            raise LedgerError("Solo las aportaciones indican persona")
        if self.amount.is_zero:
            raise LedgerError("Un movimiento no puede ser de importe cero")
        if len(self.note) > MAX_NOTE or not self.note.replace("\n", "").isprintable():
            raise LedgerError(f"La nota no puede superar {MAX_NOTE} caracteres")
        if self.category_id is not None and self.kind is not TransactionKind.EXPENSE:
            raise LedgerError("Solo los gastos tienen categoría")
        if not self.merchant:
            object.__setattr__(self, "merchant", merchant_key(self.description))

    @property
    def is_uncategorized(self) -> bool:
        return self.kind is TransactionKind.EXPENSE and self.category_id is None


def account_balance(account: Account, transactions: Iterable[Transaction]) -> Money:
    total = account.opening_balance
    for t in transactions:
        if t.account_id != account.id:
            raise LedgerError("Movimiento de otra cuenta")
        total = total + t.amount
    return total


@dataclass(frozen=True, slots=True)
class Summary:
    """Totales de un conjunto de movimientos, con las reglas del hogar."""

    spent: Money
    """Gasto neto: gastos menos devoluciones. Positivo = se ha gastado."""
    contributions: Money
    income: Money
    saved_to_savings: Money
    """Lo traspasado a hucha o ahorro."""

    @property
    def inflow(self) -> Money:
        return self.contributions + self.income

    @property
    def saved(self) -> Money:
        """Ahorro del periodo: lo que entra menos lo que se gasta."""
        return self.inflow - self.spent


def summarize(transactions: Iterable[Transaction], currency: Currency) -> Summary:
    zero = Money.zero(currency)
    spent = contributions = income = savings = zero
    for t in transactions:
        if t.kind is TransactionKind.EXPENSE:
            spent = spent - t.amount
        elif t.kind is TransactionKind.CONTRIBUTION and not t.amount.is_negative:
            contributions = contributions + t.amount
        elif t.kind is TransactionKind.INCOME:
            income = income + t.amount
        elif t.kind is TransactionKind.SAVINGS_TRANSFER:
            savings = savings - t.amount
    return Summary(spent, contributions, income, savings)
