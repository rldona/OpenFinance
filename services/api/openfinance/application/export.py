"""Exportación de los datos del hogar (OF-501).

Exporta lo que ve quien la pide: las cuentas personales de la otra persona, sus reglas
personales y sus patrones de salida no se incluyen (ADR-0013). Nunca se exportan sesiones,
hashes de contraseña, lotes de importación ni huellas de movimientos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from openfinance.application.errors import InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.application.savings import goal_saved
from openfinance.domain.categories import HOUSEHOLD_SCOPE
from openfinance.domain.imports import PatternDirection
from openfinance.domain.ledger import account_balance
from openfinance.domain.reports import to_dict as report_dict
from openfinance.domain.shared.ids import AccountId, WorkspaceId
from openfinance.domain.tags import join_tags
from openfinance.domain.workspaces import Actor

EXPORT_V1 = 1
EXPORT_FORMAT_VERSION = 2
"""Sube cuando cambie la forma del archivo exportado. La v2 (ADR-0025) añade presupuestos por
mes, aportaciones a objetivos, pagos programados, plantillas, reglas, comercios, informes
guardados y conexiones bancarias; la v1 sigue disponible."""


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
    type: str
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
    note: str
    tags: str
    """Etiquetas separadas por «|» (OF-1002)."""
    transfer_peer_id: UUID | None
    """El otro lado de un traspaso enlazado, si también lo ves (OF-1004)."""
    parts: str
    """Partes de un gasto dividido: «categoría:importe|…» (OF-1003)."""


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
class ExportedRate:
    currency: str
    on: date
    rate: str
    source: str


@dataclass(frozen=True, slots=True)
class ExportedBudgetV2:
    category_id: UUID
    amount: Decimal
    currency: str
    mode: str
    started: str | None


@dataclass(frozen=True, slots=True)
class ExportedBudgetAllocation:
    category_id: UUID
    month: str
    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class ExportedGoalContribution:
    id: UUID
    goal_id: UUID
    made_on: date
    amount: Decimal
    currency: str
    note: str


@dataclass(frozen=True, slots=True)
class ExportedScheduledPayment:
    id: UUID
    name: str
    amount: Decimal
    currency: str
    account_id: UUID
    frequency: str
    first_due: date
    interval: int
    ends_on: date | None
    category_id: UUID | None
    merchant: str
    variable: bool
    active: bool


@dataclass(frozen=True, slots=True)
class ExportedTemplate:
    id: UUID
    name: str
    scope: Literal["household", "personal"]
    kind: str
    amount: Decimal
    description: str
    account_id: UUID
    category_id: UUID | None
    tags: str
    note: str


@dataclass(frozen=True, slots=True)
class ExportedAutomationRule:
    id: UUID
    name: str
    scope: Literal["household", "personal"]
    phase: str
    priority: int
    enabled: bool
    definition: str
    """Condiciones y acciones en JSON canónico."""


@dataclass(frozen=True, slots=True)
class ExportedMerchant:
    id: UUID
    name: str
    variants: str
    """Las variantes que escribe el banco, separadas por «|»."""


@dataclass(frozen=True, slots=True)
class ExportedSavedReport:
    id: UUID
    name: str
    shared: bool
    owner_id: UUID
    definition: str
    """La definición en JSON: nunca resultados."""


@dataclass(frozen=True, slots=True)
class ExportedBankConnection:
    id: UUID
    bank: str
    country: str
    status: str
    valid_until: datetime | None
    last_sync_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExportedBankLink:
    connection_id: UUID
    name: str
    iban_tail: str
    currency: str
    account_id: UUID | None
    bank_balance: Decimal | None
    bank_balance_at: datetime | None


@dataclass(frozen=True, slots=True)
class HouseholdExport:
    meta: ExportMeta
    members: list[ExportedMember]
    accounts: list[ExportedAccount]
    transactions: list[ExportedTransaction]
    categories: list[ExportedCategory]
    rules: list[ExportedRule]
    budgets: list[ExportedBudget | ExportedBudgetV2]
    goals: list[ExportedGoal]
    member_patterns: list[ExportedPattern]
    exchange_rates: list[ExportedRate]
    # Solo en la v2 (ADR-0025):
    budget_allocations: list[ExportedBudgetAllocation] = field(default_factory=list)
    goal_contributions: list[ExportedGoalContribution] = field(default_factory=list)
    scheduled_payments: list[ExportedScheduledPayment] = field(default_factory=list)
    templates: list[ExportedTemplate] = field(default_factory=list)
    automation_rules: list[ExportedAutomationRule] = field(default_factory=list)
    merchants: list[ExportedMerchant] = field(default_factory=list)
    saved_reports: list[ExportedSavedReport] = field(default_factory=list)
    bank_connections: list[ExportedBankConnection] = field(default_factory=list)
    bank_links: list[ExportedBankLink] = field(default_factory=list)


def export_household(
    uow: UnitOfWork,
    actor: Actor,
    now: datetime,
    app_version: str,
    version: int = EXPORT_FORMAT_VERSION,
) -> HouseholdExport:
    """Todo lo que ``actor`` puede ver de su hogar. Único punto que decide la visibilidad.

    Nunca sale el identificador de sesión del agregador ni el ``state`` de una conexión, las
    claves ni las suscripciones push, las huellas, las sesiones ni los hashes (ADR-0025).
    """
    if version not in (EXPORT_V1, EXPORT_FORMAT_VERSION):
        raise InvalidRequestError("Versión de exportación no disponible")
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
        tags = uow.tags.for_transactions(household_id, [t.id for t in txns])
        splits = uow.splits.for_transactions(household_id, [t.id for t in txns])
        peers = uow.links.peers(household_id, [t.id for t in txns])
        accounts.append(
            ExportedAccount(
                id=account.id,
                name=account.name,
                institution=account.institution.value,
                kind=account.kind.value,
                type=account.type.value,
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
                note=t.note,
                tags=join_tags(tags.get(t.id, ())),
                transfer_peer_id=peers.get(t.id),
                parts="|".join(
                    f"{category_names.get(p.category_id, '')}:{p.amount.amount}"
                    for p in splits.get(t.id, [])
                ),
            )
            for t in txns
        )
    transactions.sort(key=lambda t: (t.booked_at, str(t.id)))
    # Un enlace con un movimiento que no ves no se enseña (ADR-0013).
    seen = {t.id for t in transactions}
    transactions = [
        replace(t, transfer_peer_id=t.transfer_peer_id if t.transfer_peer_id in seen else None)
        for t in transactions
    ]
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
            format_version=version,
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
        budgets=_budgets(uow, household_id, version),
        goals=goals,
        member_patterns=patterns,
        exchange_rates=[
            ExportedRate(r.currency.code, r.on, f"{r.rate:f}", r.source)
            for r in uow.rates.all(household_id)
        ],
        **(_v2_extras(uow, actor, visible_ids, transactions, now) if version >= 2 else {}),
    )


def _budgets(
    uow: UnitOfWork, household_id: WorkspaceId, version: int
) -> list[ExportedBudget | ExportedBudgetV2]:
    budgets = uow.budgets.for_household(household_id)
    if version < 2:
        return [
            ExportedBudget(
                category_id=b.category_id, amount=b.amount.amount, currency=b.amount.currency.code
            )
            for b in budgets
        ]
    return [
        ExportedBudgetV2(
            category_id=b.category_id,
            amount=b.amount.amount,
            currency=b.amount.currency.code,
            mode=b.mode.value,
            started=str(b.started) if b.started else None,
        )
        for b in budgets
    ]


def _scope_name(scope: str) -> Literal["household", "personal"]:
    return "household" if scope == HOUSEHOLD_SCOPE else "personal"


def _v2_extras(
    uow: UnitOfWork,
    actor: Actor,
    visible_ids: set[AccountId],
    transactions: list[ExportedTransaction],
    now: datetime,
) -> dict[str, list[Any]]:
    """Lo que añade la v2. Cada bloque aplica su propia regla de visibilidad (ADR-0013)."""
    household_id = actor.household_id
    own_scope = str(actor.user_id)
    allocations = [
        ExportedBudgetAllocation(category_id, str(month), amount.amount, amount.currency.code)
        for (category_id, month), amount in sorted(
            uow.budgets.overrides(household_id).items(), key=lambda i: (str(i[0][0]), str(i[0][1]))
        )
    ]
    contributions = [
        ExportedGoalContribution(
            c.id, c.goal_id, c.made_on, c.amount.amount, c.amount.currency.code, c.note
        )
        for g in uow.goals.for_household(household_id)
        for c in sorted(
            uow.goals.contributions(household_id, g.id), key=lambda c: (c.made_on, str(c.id))
        )
    ]
    payments = [
        ExportedScheduledPayment(
            p.id,
            p.name,
            p.amount.amount,
            p.amount.currency.code,
            p.account_id,
            p.frequency.value,
            p.first_due,
            p.interval,
            p.ends_on,
            p.category_id,
            p.merchant,
            p.variable,
            p.active,
        )
        for p in uow.schedule.for_household(household_id)
        if p.account_id in visible_ids
    ]
    templates = [
        ExportedTemplate(
            t.id,
            t.name,
            _scope_name(t.scope),
            t.kind.value,
            t.amount,
            t.description,
            t.account_id,
            t.category_id,
            join_tags(t.tags),
            t.note,
        )
        for t in uow.templates.for_household(household_id)
        if t.scope in (HOUSEHOLD_SCOPE, own_scope) and t.account_id in visible_ids
    ]
    automation = [
        ExportedAutomationRule(
            r.id, r.name, _scope_name(r.scope), r.phase.value, r.priority, r.enabled, r.definition()
        )
        for r in uow.automation.for_household(household_id)
        if r.scope in (HOUSEHOLD_SCOPE, own_scope)
    ]
    # Un comercio solo sale si alguno de sus nombres aparece en lo que ves: sus variantes
    # podrían delatar un gasto de una cuenta personal ajena.
    seen_merchants = {t.merchant for t in transactions}
    merchants = [
        ExportedMerchant(m.id, m.name, "|".join(m.keys))
        for m in uow.merchants.all(household_id)
        if seen_merchants & set(m.keys)
    ]
    saved = [
        ExportedSavedReport(
            r.id,
            r.name,
            r.shared,
            r.owner_id,
            json.dumps(report_dict(r.definition), ensure_ascii=False),
        )
        for r in uow.reports.visible_to(household_id, actor.user_id)
    ]
    connections = [c.current(now) for c in uow.bank.for_owner(household_id, actor.user_id)]
    return {
        "budget_allocations": allocations,
        "goal_contributions": contributions,
        "scheduled_payments": payments,
        "templates": templates,
        "automation_rules": automation,
        "merchants": merchants,
        "saved_reports": saved,
        "bank_connections": [
            ExportedBankConnection(
                c.id, c.aspsp, c.country, c.status.value, c.valid_until, c.last_sync_at
            )
            for c in connections
        ],
        "bank_links": [
            ExportedBankLink(
                c.id,
                link.name,
                link.iban_tail,
                link.currency,
                link.account_id if link.account_id in visible_ids else None,
                link.bank_balance.amount if link.bank_balance else None,
                link.bank_balance_at,
            )
            for c in connections
            for link in c.links
        ],
    }
