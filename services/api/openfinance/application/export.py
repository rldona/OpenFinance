"""Exportación de los datos del hogar (OF-501).

Exporta lo que ve quien la pide: las cuentas personales de la otra persona, sus reglas
personales y sus patrones de salida no se incluyen (ADR-0013). Nunca se exportan sesiones,
hashes de contraseña, lotes de importación ni huellas de movimientos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from openfinance.application.errors import NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.application.savings import goal_saved
from openfinance.domain.categories import HOUSEHOLD_SCOPE
from openfinance.domain.imports import PatternDirection
from openfinance.domain.ledger import account_balance
from openfinance.domain.workspaces import Actor

EXPORT_FORMAT_VERSION = 1
"""Sube cuando cambie la forma del archivo exportado."""


@dataclass(frozen=True, slots=True)
class ExportMeta:
    format_version: int
    app_version: str
    exported_at: datetime
    household_id: UUID
    household_name: str
    exported_by_id: UUID
    exported_by_name: str
    exported_by_email: str


@dataclass(frozen=True, slots=True)
class ExportedMember:
    id: UUID
    display_name: str


@dataclass(frozen=True, slots=True)
class ExportedAccount:
    id: UUID
    name: str
    institution: str
    kind: str
    currency: str
    opening_balance: Decimal
    balance: Decimal
    owner_id: UUID | None


@dataclass(frozen=True, slots=True)
class ExportedTransaction:
    id: UUID
    account_id: UUID
    booked_at: datetime
    value_date: date
    description: str
    merchant: str
    amount: Decimal
    currency: str
    kind: str
    category_id: UUID | None
    category: str | None
    member_id: UUID | None
    member: str | None
    bank_type: str
    source: str


@dataclass(frozen=True, slots=True)
class ExportedCategory:
    id: UUID
    name: str
    icon: str
    color: str
    hidden: bool
    position: int


@dataclass(frozen=True, slots=True)
class ExportedRule:
    merchant: str
    category_id: UUID
    scope: Literal["household", "personal"]


@dataclass(frozen=True, slots=True)
class ExportedBudget:
    category_id: UUID
    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class ExportedGoal:
    id: UUID
    name: str
    icon: str
    target: Decimal
    monthly: Decimal
    saved: Decimal
    currency: str
    deadline: str | None
    account_id: UUID | None


@dataclass(frozen=True, slots=True)
class ExportedPattern:
    member_id: UUID
    direction: str
    pattern: str


@dataclass(frozen=True, slots=True)
class HouseholdExport:
    meta: ExportMeta
    members: list[ExportedMember]
    accounts: list[ExportedAccount]
    transactions: list[ExportedTransaction]
    categories: list[ExportedCategory]
    rules: list[ExportedRule]
    budgets: list[ExportedBudget]
    goals: list[ExportedGoal]
    member_patterns: list[ExportedPattern]


def export_household(
    uow: UnitOfWork, actor: Actor, now: datetime, app_version: str
) -> HouseholdExport:
    """Todo lo que ``actor`` puede ver de su hogar. Único punto que decide la visibilidad."""
    household_id = actor.household_id
    user = uow.users.get(actor.user_id)
    household = uow.households.get(household_id)
    if user is None or household is None:
        raise NotFoundError("Sesión sin usuario u hogar")
    members = uow.households.members(household_id)
    names = {m.id: m.display_name for m in members}
    categories = uow.categories.for_household(household_id)
    category_names = {c.id: c.name for c in categories}

    accounts: list[ExportedAccount] = []
    transactions: list[ExportedTransaction] = []
    visible = visible_accounts(uow, actor)
    for account in visible:
        txns = uow.transactions.for_account(household_id, account.id)
        accounts.append(
            ExportedAccount(
                id=account.id,
                name=account.name,
                institution=account.institution.value,
                kind=account.kind.value,
                currency=account.currency.code,
                opening_balance=account.opening_balance.amount,
                balance=account_balance(account, txns).amount,
                owner_id=account.owner_id,
            )
        )
        transactions.extend(
            ExportedTransaction(
                id=t.id,
                account_id=t.account_id,
                booked_at=t.booked_at,
                value_date=t.value_date,
                description=t.description,
                merchant=t.merchant,
                amount=t.amount.amount,
                currency=t.amount.currency.code,
                kind=t.kind.value,
                category_id=t.category_id,
                category=category_names.get(t.category_id) if t.category_id else None,
                member_id=t.member_id,
                member=names.get(t.member_id) if t.member_id else None,
                bank_type=t.bank_type,
                source=t.source,
            )
            for t in txns
        )
    transactions.sort(key=lambda t: (t.booked_at, str(t.id)))
    visible_ids = {a.id for a in visible}

    own_scope = str(actor.user_id)
    rules = [
        ExportedRule(
            merchant=r.merchant,
            category_id=r.category_id,
            scope="household" if r.scope == HOUSEHOLD_SCOPE else "personal",
        )
        for r in uow.rules.for_household(household_id)
        if r.scope in (HOUSEHOLD_SCOPE, own_scope)
    ]
    patterns = [
        ExportedPattern(member_id=p.user_id, direction=p.direction.value, pattern=p.pattern)
        for p in uow.member_patterns.for_household(household_id)
        if p.user_id == actor.user_id or p.direction is PatternDirection.INFLOW
    ]
    goals = [
        ExportedGoal(
            id=g.id,
            name=g.name,
            icon=g.icon,
            target=g.target.amount,
            monthly=g.monthly.amount,
            saved=goal_saved(uow, actor, g).amount,
            currency=g.target.currency.code,
            deadline=str(g.deadline) if g.deadline else None,
            account_id=g.account_id if g.account_id in visible_ids else None,
        )
        for g in uow.goals.for_household(household_id)
    ]
    return HouseholdExport(
        meta=ExportMeta(
            format_version=EXPORT_FORMAT_VERSION,
            app_version=app_version,
            exported_at=now,
            household_id=household.id,
            household_name=household.name,
            exported_by_id=user.id,
            exported_by_name=user.display_name,
            exported_by_email=user.email,
        ),
        members=[ExportedMember(id=m.id, display_name=m.display_name) for m in members],
        accounts=accounts,
        transactions=transactions,
        categories=[
            ExportedCategory(
                id=c.id,
                name=c.name,
                icon=c.icon,
                color=c.color,
                hidden=c.hidden,
                position=c.position,
            )
            for c in categories
        ],
        rules=rules,
        budgets=[
            ExportedBudget(
                category_id=b.category_id, amount=b.amount.amount, currency=b.amount.currency.code
            )
            for b in uow.budgets.for_household(household_id)
        ],
        goals=goals,
        member_patterns=patterns,
    )
