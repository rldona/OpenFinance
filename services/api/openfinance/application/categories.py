"""Categorías, corrección de categoría y reglas aprendidas (OF-201, OF-202, OF-203)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from openfinance.application.changes import record, transaction_state
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import TransactionQuery, UnitOfWork
from openfinance.domain.categories import (
    DEFAULT_CATEGORIES,
    HOUSEHOLD_SCOPE,
    Category,
    CategoryError,
    CategoryId,
    CategoryRule,
    can_learn,
    is_person_transfer,
    merchant_label,
    rule_matches,
)
from openfinance.domain.changes import Change, Entity, diff, rule_entity_id
from openfinance.domain.ledger import (
    Account,
    AccountKind,
    LedgerError,
    Transaction,
    TransactionKind,
    normalize_note,
)
from openfinance.domain.shared.ids import TransactionId, UserId, WorkspaceId
from openfinance.domain.workspaces import Actor


def rule_scope(account: Account) -> str:
    """Las reglas aprendidas en una cuenta personal solo son de su titular (ADR-0013)."""
    if account.kind is AccountKind.PERSONAL and account.owner_id is not None:
        return str(account.owner_id)
    return HOUSEHOLD_SCOPE


def rules_for_account(uow: UnitOfWork, account: Account) -> list[CategoryRule]:
    """Reglas aplicables a una cuenta: las del hogar y, en una personal, las de su titular."""
    scopes = {HOUSEHOLD_SCOPE, rule_scope(account)}
    return [r for r in uow.rules.for_household(account.household_id) if r.scope in scopes]


def seed_default_categories(uow: UnitOfWork, household_id: WorkspaceId) -> None:
    for position, d in enumerate(DEFAULT_CATEGORIES):
        uow.categories.add(
            Category(
                id=CategoryId(uuid4()),
                household_id=household_id,
                name=d.name,
                icon=d.icon,
                color=d.color,
                slug=d.slug,
                position=position,
            )
        )


def list_categories(uow: UnitOfWork, actor: Actor) -> list[Category]:
    return uow.categories.for_household(actor.household_id)


def _check_unique(uow: UnitOfWork, category: Category) -> None:
    for other in uow.categories.for_household(category.household_id):
        if other.id != category.id and other.key == category.key:
            raise ConflictError(f"Ya existe la categoría «{other.name}»")


def create_category(uow: UnitOfWork, actor: Actor, name: str, icon: str, color: str) -> Category:
    existing = uow.categories.for_household(actor.household_id)
    try:
        category = Category(
            id=CategoryId(uuid4()),
            household_id=actor.household_id,
            name=name.strip(),
            icon=icon.strip(),
            color=color,
            position=max((c.position for c in existing), default=-1) + 1,
        )
    except CategoryError as exc:
        raise InvalidRequestError(str(exc)) from exc
    _check_unique(uow, category)
    uow.categories.add(category)
    uow.commit()
    return category


def update_category(
    uow: UnitOfWork,
    actor: Actor,
    category_id: CategoryId,
    *,
    name: str | None = None,
    icon: str | None = None,
    color: str | None = None,
    hidden: bool | None = None,
) -> Category:
    """Renombrar, cambiar icono o color, u ocultar. Ocultar no toca los movimientos."""
    current = uow.categories.get(actor.household_id, category_id)
    if current is None:
        raise NotFoundError("Categoría no encontrada")
    try:
        updated = replace(
            current,
            name=name.strip() if name is not None else current.name,
            icon=icon.strip() if icon is not None else current.icon,
            color=color if color is not None else current.color,
            hidden=hidden if hidden is not None else current.hidden,
        )
    except CategoryError as exc:
        raise InvalidRequestError(str(exc)) from exc
    _check_unique(uow, updated)
    uow.categories.update(updated)
    uow.commit()
    return updated


@dataclass(frozen=True, slots=True)
class TransactionEdit:
    """Qué corregir de un movimiento. Lo que es ``None`` no cambia."""

    kind: TransactionKind | None = None
    member_id: UserId | None = None
    note: str | None = None
    set_category: bool = False
    """Si se pone o quita la categoría (``category_id``; ``None`` = quitarla)."""
    category_id: CategoryId | None = None
    learn: bool = True


@dataclass(frozen=True, slots=True)
class CategorizeResult:
    transaction: Transaction
    rule: CategoryRule | None
    also_categorized: int
    operation_id: UUID | None = None
    """Operación del registro de cambios, para «Deshacer» (ADR-0017)."""


KIND_LABELS = {
    TransactionKind.EXPENSE: "Gasto",
    TransactionKind.INCOME: "Ingreso",
    TransactionKind.CONTRIBUTION: "Aportación",
    TransactionKind.SAVINGS_TRANSFER: "Hucha",
    TransactionKind.INTERNAL_TRANSFER: "Entre cuentas",
}


def categorize_transaction(
    uow: UnitOfWork,
    actor: Actor,
    transaction_id: TransactionId,
    category_id: CategoryId | None,
    now: datetime,
    *,
    learn: bool = True,
) -> CategorizeResult:
    """Pone o quita la categoría de un gasto (ver ``edit_transaction``)."""
    edit = TransactionEdit(set_category=True, category_id=category_id, learn=learn)
    return edit_transaction(uow, actor, transaction_id, edit, now)


def edit_transaction(
    uow: UnitOfWork,
    actor: Actor,
    transaction_id: TransactionId,
    edit: TransactionEdit,
    now: datetime,
) -> CategorizeResult:
    """Corrige tipo, persona, nota o categoría de un movimiento y lo deja en el registro.

    El importe, la fecha, el concepto y la huella nunca cambian. Un movimiento que deja de
    ser gasto pierde su categoría, y uno que deja de ser aportación, su persona.

    Al poner una categoría con ``learn``, guarda la regla «comercio → categoría» y la aplica a
    los gastos sin categoría del mismo comercio; nunca cambia una categoría elegida. Al
    quitarla, borra la regla. Una regla aprendida en una cuenta personal es solo de su titular
    y solo afecta a sus cuentas personales; una del hogar, a las cuentas que el usuario ve.
    Todo va en una sola operación: «Deshacer» lo revierte junto.
    """
    tx = uow.transactions.get(actor.household_id, transaction_id)
    visible = visible_accounts(uow, actor)
    account = next((a for a in visible if tx is not None and a.id == tx.account_id), None)
    if tx is None or account is None:
        raise NotFoundError("Movimiento no encontrado")

    kind = edit.kind or tx.kind
    member = None
    if kind is TransactionKind.CONTRIBUTION:
        member = edit.member_id or tx.member_id
        if member is None:
            raise InvalidRequestError("Una aportación necesita indicar de quién es")
        if member not in {m.id for m in uow.households.members(actor.household_id)}:
            raise InvalidRequestError("Esa persona no es del hogar")
    elif edit.member_id is not None:
        raise InvalidRequestError("Solo las aportaciones indican persona")

    category: Category | None = None
    category_id = tx.category_id if kind is TransactionKind.EXPENSE else None
    if edit.set_category:
        if kind is not TransactionKind.EXPENSE:
            raise InvalidRequestError("Solo los gastos tienen categoría")
        if edit.category_id is not None:
            category = uow.categories.get(actor.household_id, edit.category_id)
            if category is None:
                raise NotFoundError("Categoría no encontrada")
            if category.hidden and tx.category_id != edit.category_id:
                raise InvalidRequestError(f"La categoría «{category.name}» está oculta")
        category_id = edit.category_id

    note = tx.note if edit.note is None else normalize_note(edit.note)
    try:
        updated = replace(tx, kind=kind, member_id=member, category_id=category_id, note=note)
    except LedgerError as exc:
        raise InvalidRequestError(str(exc)) from exc
    changes = diff(
        Entity.TRANSACTION, str(tx.id), transaction_state(tx), transaction_state(updated)
    )
    uow.transactions.save(updated)

    scope = rule_scope(account)
    rule: CategoryRule | None = None
    others: list[TransactionId] = []
    learns = can_learn(tx.merchant) and not is_person_transfer(tx.description, tx.bank_type)
    if edit.set_category and edit.learn and learns:
        previous = uow.rules.get(actor.household_id, scope, tx.merchant)
        if category is None:
            uow.rules.delete(actor.household_id, scope, tx.merchant)
        elif not category.hidden:
            rule = CategoryRule(actor.household_id, tx.merchant, category.id, scope)
            uow.rules.upsert(rule, now)
            # Regla del hogar: todas las cuentas visibles. Regla personal: solo las cuentas
            # personales de su titular.
            targets = [a.id for a in visible if scope == HOUSEHOLD_SCOPE or rule_scope(a) == scope]
            others = [
                t.id
                for t in uow.transactions.uncategorized_with_merchant_word(
                    actor.household_id, targets, tx.merchant.split()[0]
                )
                if t.id != tx.id and rule_matches(rule.merchant, t.merchant)
            ]
            uow.transactions.set_category(actor.household_id, others, category.id)
        before = str(previous.category_id) if previous else None
        after = str(rule.category_id) if rule else None
        if before != after:
            changes.append(
                Change(
                    Entity.RULE, rule_entity_id(scope, tx.merchant), "category_id", before, after
                )
            )
        changes += [Change(Entity.TRANSACTION, str(i), "category_id", None, after) for i in others]

    operation = record(uow, actor, "transaction.edit", _summary(uow, tx, updated), changes, now)
    uow.commit()
    return CategorizeResult(updated, rule, len(others), operation.id if operation else None)


def _summary(uow: UnitOfWork, before: Transaction, after: Transaction) -> str:
    """Resumen legible: «Mercadona: Sin categoría → Supermercado».

    Sin contar los demás que clasificó la regla: ese número depende de quién lo lee
    (``changes.display_summary``), porque puede incluir cuentas personales.
    """
    what = merchant_label(before.merchant) or before.description
    parts: list[str] = []
    if before.kind is not after.kind or before.member_id != after.member_id:
        parts.append(f"{_kind_label(uow, before)} → {_kind_label(uow, after)}")
    if before.category_id != after.category_id and after.kind is TransactionKind.EXPENSE:
        parts.append(f"{_category_name(uow, before)} → {_category_name(uow, after)}")
    if before.note != after.note:
        parts.append("nota")
    return f"{what}: {', '.join(parts) or 'sin cambios'}"


def _kind_label(uow: UnitOfWork, t: Transaction) -> str:
    if t.kind is TransactionKind.CONTRIBUTION and t.member_id is not None:
        member = uow.users.get(t.member_id)
        return f"Aportación de {member.display_name}" if member else "Aportación"
    return KIND_LABELS[t.kind]


def _category_name(uow: UnitOfWork, t: Transaction) -> str:
    if t.category_id is None:
        return "Sin categoría"
    category = uow.categories.get(t.household_id, t.category_id)
    return category.name if category else "Categoría"


@dataclass(frozen=True, slots=True)
class RuleView:
    rule: CategoryRule
    personal: bool
    """Aprendida en una cuenta personal: solo la ve y la aplica su titular (ADR-0013)."""
    matches: int
    """Movimientos con esa categoría cuyo comercio coincide con la regla."""


def list_rules(uow: UnitOfWork, actor: Actor) -> list[RuleView]:
    """Las reglas del hogar y las personales propias. Nunca las personales de la pareja."""
    own = str(actor.user_id)
    rules = [
        r for r in uow.rules.for_household(actor.household_id) if r.scope in (HOUSEHOLD_SCOPE, own)
    ]
    visible = visible_accounts(uow, actor)
    by_category: dict[CategoryId, list[Transaction]] = {}
    views: list[RuleView] = []
    for rule in rules:
        if rule.category_id not in by_category:
            ids = [a.id for a in visible]
            query = TransactionQuery(category_id=rule.category_id, limit=5000)
            by_category[rule.category_id] = (
                uow.transactions.search(actor.household_id, ids, query) if ids else []
            )
        targets = {
            a.id for a in visible if rule.scope == HOUSEHOLD_SCOPE or rule_scope(a) == rule.scope
        }
        matches = sum(
            1
            for t in by_category[rule.category_id]
            if t.account_id in targets and rule_matches(rule.merchant, t.merchant)
        )
        views.append(RuleView(rule, rule.scope != HOUSEHOLD_SCOPE, matches))
    views.sort(key=lambda v: (v.personal, v.rule.merchant))
    return views


def delete_rule(
    uow: UnitOfWork, actor: Actor, personal: bool, merchant: str, now: datetime
) -> UUID | None:
    """Borra una regla del hogar o una personal propia. Los movimientos ya clasificados no
    cambian. Queda en el registro y se puede deshacer."""
    scope = str(actor.user_id) if personal else HOUSEHOLD_SCOPE
    rule = uow.rules.get(actor.household_id, scope, merchant)
    if rule is None:
        raise NotFoundError("Regla no encontrada")
    uow.rules.delete(actor.household_id, scope, merchant)
    change = Change(
        Entity.RULE, rule_entity_id(scope, merchant), "category_id", str(rule.category_id), None
    )
    summary = f"Regla borrada: {merchant_label(merchant)}"
    operation = record(uow, actor, "rule.delete", summary, [change], now)
    uow.commit()
    return operation.id if operation else None


def uncategorized_count(uow: UnitOfWork, actor: Actor) -> int:
    accounts = [a.id for a in visible_accounts(uow, actor)]
    return uow.transactions.count_uncategorized(actor.household_id, accounts) if accounts else 0
