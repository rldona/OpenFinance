"""Categorías, corrección de categoría y reglas aprendidas (OF-201, OF-202, OF-203)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import uuid4

from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import (
    DEFAULT_CATEGORIES,
    HOUSEHOLD_SCOPE,
    Category,
    CategoryError,
    CategoryId,
    CategoryRule,
    can_learn,
    rule_matches,
)
from openfinance.domain.ledger import Account, AccountKind, Transaction, TransactionKind
from openfinance.domain.shared.ids import TransactionId, WorkspaceId
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
class CategorizeResult:
    transaction: Transaction
    rule: CategoryRule | None
    also_categorized: int


def categorize_transaction(
    uow: UnitOfWork,
    actor: Actor,
    transaction_id: TransactionId,
    category_id: CategoryId | None,
    now: datetime,
    *,
    learn: bool = True,
) -> CategorizeResult:
    """Pone o quita la categoría de un gasto.

    Con ``learn``:
    - al poner una categoría, guarda la regla «comercio → categoría» y la aplica a los gastos
      sin categoría del mismo comercio. Nunca cambia una categoría ya elegida;
    - al quitarla, borra la regla de ese comercio.
    Una regla aprendida en una cuenta personal es solo de su titular y solo afecta a sus
    cuentas personales; una del hogar afecta a las cuentas que el usuario puede ver.
    """
    tx = uow.transactions.get(actor.household_id, transaction_id)
    visible = visible_accounts(uow, actor)
    account = next((a for a in visible if tx is not None and a.id == tx.account_id), None)
    if tx is None or account is None:
        raise NotFoundError("Movimiento no encontrado")
    if tx.kind is not TransactionKind.EXPENSE:
        raise InvalidRequestError("Solo los gastos tienen categoría")
    category: Category | None = None
    if category_id is not None:
        category = uow.categories.get(actor.household_id, category_id)
        if category is None:
            raise NotFoundError("Categoría no encontrada")
        if category.hidden and tx.category_id != category_id:
            raise InvalidRequestError(f"La categoría «{category.name}» está oculta")

    uow.transactions.set_category(actor.household_id, [tx.id], category_id)
    updated = replace(tx, category_id=category_id)

    scope = rule_scope(account)
    rule: CategoryRule | None = None
    others = 0
    if learn and can_learn(tx.merchant):
        if category is None:
            uow.rules.delete(actor.household_id, scope, tx.merchant)
        elif not category.hidden:
            rule = CategoryRule(actor.household_id, tx.merchant, category.id, scope)
            uow.rules.upsert(rule, now)
            # Regla del hogar: todas las cuentas visibles. Regla personal: solo las cuentas
            # personales de su titular.
            targets = [a.id for a in visible if scope == HOUSEHOLD_SCOPE or rule_scope(a) == scope]
            candidates = [
                t.id
                for t in uow.transactions.uncategorized_with_merchant_word(
                    actor.household_id, targets, tx.merchant.split()[0]
                )
                if t.id != tx.id and rule_matches(rule.merchant, t.merchant)
            ]
            uow.transactions.set_category(actor.household_id, candidates, category.id)
            others = len(candidates)
    uow.commit()
    return CategorizeResult(updated, rule, others)


def uncategorized_count(uow: UnitOfWork, actor: Actor) -> int:
    accounts = [a.id for a in visible_accounts(uow, actor)]
    return uow.transactions.count_uncategorized(actor.household_id, accounts) if accounts else 0
