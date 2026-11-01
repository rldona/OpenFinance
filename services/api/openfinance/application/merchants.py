"""Comercios: renombrar y fusionar (OF-1001).

Un comercio agrupa las variantes con las que el banco escribe su nombre. Se ve lo que
aparece en las cuentas que ve quien pregunta: un comercio que solo existe en la cuenta
personal de la pareja no aparece, ni se puede renombrar o fusionar (ADR-0013).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from openfinance.application import changes as change_log
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import HOUSEHOLD_SCOPE, CategoryRule, merchant_label
from openfinance.domain.changes import Change, Entity, rule_entity_id
from openfinance.domain.ledger import Transaction
from openfinance.domain.merchants import (
    Merchant,
    MerchantError,
    MerchantId,
    clean_name,
    join_keys,
)
from openfinance.domain.shared.ids import AccountId, WorkspaceId
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class MerchantView:
    id: UUID | None
    """``None`` si nadie le ha puesto nombre propio todavía."""
    name: str
    keys: list[str]
    """Solo las variantes que aparecen en las cuentas que ve quien pregunta."""
    count: int
    total: Decimal
    """Suma de sus movimientos (los gastos suman en negativo)."""


def _visible_ids(uow: UnitOfWork, actor: Actor) -> list[AccountId]:
    return [a.id for a in visible_accounts(uow, actor)]


def list_merchants(uow: UnitOfWork, actor: Actor) -> list[MerchantView]:
    totals = uow.transactions.merchant_totals(actor.household_id, _visible_ids(uow, actor))
    stored = uow.merchants.for_keys(actor.household_id, [k for k, _, _ in totals])
    groups: dict[object, MerchantView] = {}
    for key, count, total in totals:
        merchant = stored.get(key)
        group_id: object = merchant.id if merchant else key
        current = groups.get(group_id)
        if current is None:
            groups[group_id] = MerchantView(
                merchant.id if merchant else None,
                merchant.name if merchant else merchant_label(key),
                [key],
                count,
                total,
            )
        else:
            groups[group_id] = MerchantView(
                current.id,
                current.name,
                sorted([*current.keys, key]),
                current.count + count,
                current.total + total,
            )
    return sorted(groups.values(), key=lambda m: (-m.count, m.name.casefold()))


def names_for(
    uow: UnitOfWork, household_id: WorkspaceId, transactions: Iterable[Transaction]
) -> dict[str, str]:
    """Nombre propio de cada variante que lo tenga, para enseñarlo en los movimientos."""
    keys = sorted({t.merchant for t in transactions if t.merchant})
    return {k: m.name for k, m in uow.merchants.for_keys(household_id, keys).items()}


def _find(views: list[MerchantView], key: str) -> MerchantView:
    view = next((v for v in views if key in v.keys), None)
    if view is None:
        raise NotFoundError("Comercio no encontrado")
    return view


def _ensure(uow: UnitOfWork, actor: Actor, view: MerchantView, changes: list[Change]) -> Merchant:
    """El comercio guardado de esa vista; si no lo tenía, lo crea (y lo anota para deshacer)."""
    if view.id is not None:
        merchant = uow.merchants.get(actor.household_id, MerchantId(view.id))
        if merchant is not None:
            return merchant
    merchant = Merchant(MerchantId(uuid4()), actor.household_id, view.name, tuple(view.keys))
    uow.merchants.add(merchant)
    changes.append(Change(Entity.MERCHANT, str(merchant.id), "name", None, merchant.name))
    changes.append(
        Change(Entity.MERCHANT, str(merchant.id), "keys", None, join_keys(merchant.keys))
    )
    return merchant


def rename_merchant(
    uow: UnitOfWork, actor: Actor, key: str, name: str, now: datetime
) -> tuple[MerchantView, UUID | None]:
    try:
        new_name = clean_name(name)
    except MerchantError as exc:
        raise InvalidRequestError(str(exc)) from exc
    views = list_merchants(uow, actor)
    view = _find(views, key)
    if new_name == view.name:
        return view, None
    if any(v is not view and v.name.casefold() == new_name.casefold() for v in views):
        raise ConflictError("Ya hay un comercio con ese nombre: fusiónalos si son el mismo")
    changes: list[Change] = []
    merchant = uow.merchants.get(actor.household_id, MerchantId(view.id)) if view.id else None
    if merchant is None:
        merchant = Merchant(MerchantId(uuid4()), actor.household_id, new_name, tuple(view.keys))
        uow.merchants.add(merchant)
        eid = str(merchant.id)
        changes.append(Change(Entity.MERCHANT, eid, "name", None, new_name))
        changes.append(Change(Entity.MERCHANT, eid, "keys", None, join_keys(merchant.keys)))
    else:
        uow.merchants.set_name(actor.household_id, merchant.id, new_name)
        changes.append(Change(Entity.MERCHANT, str(merchant.id), "name", merchant.name, new_name))
    operation = change_log.record(
        uow,
        actor,
        "merchant.rename",
        f"Comercio «{view.name}» renombrado a «{new_name}»",
        changes,
        now,
    )
    uow.commit()
    renamed = _find(list_merchants(uow, actor), key)
    return renamed, operation.id if operation else None


@dataclass(frozen=True, slots=True)
class MergeResult:
    merchant: MerchantView
    reclassified: int
    """Gastos sin categoría que han tomado la categoría del comercio de destino."""
    operation_id: UUID | None


def merge_merchants(
    uow: UnitOfWork, actor: Actor, target_key: str, source_key: str, now: datetime
) -> MergeResult:
    """Pasa las variantes de ``source`` a ``target`` y borra ``source``.

    Si el destino tiene una regla de categoría, los gastos sin categoría del origen (solo los
    que ve quien fusiona) la toman, y el origen aprende esa regla para las próximas
    importaciones. Todo se deshace de una vez.
    """
    views = list_merchants(uow, actor)
    target_view, source_view = _find(views, target_key), _find(views, source_key)
    if target_view is source_view:
        raise InvalidRequestError("Esos dos ya son el mismo comercio")
    changes: list[Change] = []
    target = _ensure(uow, actor, target_view, changes)
    source = _ensure(uow, actor, source_view, changes)
    merged = tuple(sorted({*target.keys, *source.keys}))
    # Orden de los cambios: al deshacer se recorren al revés y el destino suelta las variantes
    # antes de que el origen las recupere.
    changes += [
        Change(Entity.MERCHANT, str(source.id), "name", source.name, None),
        Change(Entity.MERCHANT, str(source.id), "keys", join_keys(source.keys), None),
        Change(Entity.MERCHANT, str(target.id), "keys", join_keys(target.keys), join_keys(merged)),
    ]
    uow.merchants.delete(actor.household_id, source.id)
    uow.merchants.set_keys(actor.household_id, target.id, list(merged))

    category = next(
        (
            rule.category_id
            for key in target.keys
            if (rule := uow.rules.get(actor.household_id, HOUSEHOLD_SCOPE, key)) is not None
        ),
        None,
    )
    reclassified = 0
    if category is not None:
        accounts = _visible_ids(uow, actor)
        for key in source_view.keys:
            for t in uow.transactions.uncategorized_with_merchant(
                actor.household_id, accounts, key
            ):
                uow.transactions.save(replace(t, category_id=category))
                changes.append(
                    Change(Entity.TRANSACTION, str(t.id), "category_id", None, str(category))
                )
                reclassified += 1
        for key in source.keys:
            if uow.rules.get(actor.household_id, HOUSEHOLD_SCOPE, key) is None:
                uow.rules.upsert(
                    CategoryRule(actor.household_id, key, category, HOUSEHOLD_SCOPE), now
                )
                changes.append(
                    Change(
                        Entity.RULE,
                        rule_entity_id(HOUSEHOLD_SCOPE, key),
                        "category_id",
                        None,
                        str(category),
                    )
                )
    operation = change_log.record(
        uow,
        actor,
        "merchant.merge",
        f"Comercio «{source_view.name}» fusionado en «{target_view.name}»",
        changes,
        now,
    )
    uow.commit()
    return MergeResult(
        _find(list_merchants(uow, actor), target_key),
        reclassified,
        operation.id if operation else None,
    )
