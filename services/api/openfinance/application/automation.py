"""Reglas con condiciones, acciones y fases: crear, probar y aplicar (ADR-0020, OF-1101/1102).

Una regla del hogar ve y cambia los movimientos de las cuentas que ve quien la aplica; una
personal, solo los de las cuentas personales de su titular (ADR-0013). Un recuento nunca incluye
lo que no se ve. Toda escritura va en el registro de cambios y se deshace de una vez.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from openfinance.application import changes as change_log
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.automation import (
    GENERIC_KINDS,
    AutomationRule,
    Decision,
    Fixed,
    Phase,
    RowView,
    RuleError,
    clean_name,
    decide,
    parse_actions,
    parse_conditions,
)
from openfinance.domain.categories import HOUSEHOLD_SCOPE, CategoryId
from openfinance.domain.changes import Change, Entity
from openfinance.domain.ledger import Account, AccountKind, Transaction, TransactionKind
from openfinance.domain.shared.ids import AccountId, WorkspaceId
from openfinance.domain.tags import join_tags, split_tags
from openfinance.domain.workspaces import Actor

MAX_RULES = 200
PREVIEW_LIMIT = 100


def personal_scope(actor: Actor) -> str:
    return str(actor.user_id)


def visible_rules(uow: UnitOfWork, actor: Actor) -> list[AutomationRule]:
    """Las reglas del hogar y las personales propias. Las personales de la pareja no existen."""
    scopes = {HOUSEHOLD_SCOPE, personal_scope(actor)}
    return [r for r in uow.automation.for_household(actor.household_id) if r.scope in scopes]


def rules_for_account(
    uow: UnitOfWork, household_id: WorkspaceId, account: Account
) -> list[AutomationRule]:
    """Reglas que aplican a una cuenta: las del hogar y, en una personal, las de su titular."""
    scopes = {HOUSEHOLD_SCOPE}
    if account.kind is AccountKind.PERSONAL and account.owner_id is not None:
        scopes.add(str(account.owner_id))
    return [r for r in uow.automation.for_household(household_id) if r.scope in scopes]


def _own(uow: UnitOfWork, actor: Actor, rule_id: UUID) -> AutomationRule:
    rule = uow.automation.get(actor.household_id, rule_id)
    if rule is None or rule.scope not in (HOUSEHOLD_SCOPE, personal_scope(actor)):
        raise NotFoundError("Regla no encontrada")
    return rule


@dataclass(frozen=True, slots=True)
class RuleDraft:
    name: str
    personal: bool
    phase: Phase
    priority: int | None
    enabled: bool
    conditions: Sequence[Mapping[str, Any]]
    actions: Sequence[Mapping[str, Any]]


def _build(
    uow: UnitOfWork, actor: Actor, draft: RuleDraft, rule_id: UUID, default_priority: int
) -> AutomationRule:
    try:
        conditions = parse_conditions(draft.conditions)
        actions = parse_actions(draft.actions)
        name = clean_name(draft.name)
    except RuleError as exc:
        raise InvalidRequestError(str(exc)) from exc
    scope = personal_scope(actor) if draft.personal else HOUSEHOLD_SCOPE
    visible = {a.id: a for a in visible_accounts(uow, actor)}
    for c in conditions:
        if c.field != "account":
            continue
        for account_id in c.value:
            account = visible.get(AccountId(UUID(account_id)))
            if account is None:
                raise InvalidRequestError("Una de las cuentas de la regla no existe")
            # Una regla del hogar no puede nombrar una cuenta personal (la veríais los dos).
            if scope == HOUSEHOLD_SCOPE and account.kind is AccountKind.PERSONAL:
                raise InvalidRequestError(
                    "Una regla del hogar no puede usar una cuenta personal: hazla personal"
                )
    for a in actions:
        if a.type == "set_category":
            category = uow.categories.get(actor.household_id, CategoryId(UUID(a.value)))
            if category is None:
                raise InvalidRequestError("Categoría no encontrada")
            if category.hidden:
                raise InvalidRequestError(f"La categoría «{category.name}» está oculta")
    return AutomationRule(
        id=rule_id,
        household_id=actor.household_id,
        scope=scope,
        name=name,
        phase=draft.phase,
        priority=draft.priority if draft.priority is not None else default_priority,
        enabled=draft.enabled,
        conditions=conditions,
        actions=actions,
    )


def create_rule(
    uow: UnitOfWork, actor: Actor, draft: RuleDraft, now: datetime
) -> tuple[AutomationRule, UUID | None]:
    existing = visible_rules(uow, actor)
    if len(uow.automation.for_household(actor.household_id)) >= MAX_RULES:
        raise ConflictError(f"El hogar ya tiene {MAX_RULES} reglas")
    if any(r.name.casefold() == draft.name.strip().casefold() for r in existing):
        raise ConflictError("Ya hay una regla con ese nombre")
    default = max((r.priority for r in existing), default=0) + 10
    rule = _build(uow, actor, draft, uuid4(), default)
    uow.automation.save(rule, actor.user_id)
    operation = change_log.record(
        uow,
        actor,
        "automation.create",
        f"Regla «{rule.name}» creada",
        [Change(Entity.AUTOMATION, str(rule.id), "definition", None, rule.definition())],
        now,
    )
    uow.commit()
    return rule, operation.id if operation else None


def update_rule(
    uow: UnitOfWork, actor: Actor, rule_id: UUID, draft: RuleDraft, now: datetime
) -> tuple[AutomationRule, UUID | None]:
    before = _own(uow, actor, rule_id)
    if any(
        r.id != rule_id and r.name.casefold() == draft.name.strip().casefold()
        for r in visible_rules(uow, actor)
    ):
        raise ConflictError("Ya hay una regla con ese nombre")
    updated = _build(uow, actor, draft, rule_id, before.priority)
    if updated.scope != before.scope:
        raise InvalidRequestError("Una regla no cambia de ámbito: crea otra")
    if updated.definition() == before.definition():
        return before, None
    uow.automation.save(updated, actor.user_id)
    operation = change_log.record(
        uow,
        actor,
        "automation.update",
        f"Regla «{updated.name}» cambiada",
        [
            Change(
                Entity.AUTOMATION,
                str(rule_id),
                "definition",
                before.definition(),
                updated.definition(),
            )
        ],
        now,
    )
    uow.commit()
    return updated, operation.id if operation else None


def delete_rule(uow: UnitOfWork, actor: Actor, rule_id: UUID, now: datetime) -> UUID | None:
    rule = _own(uow, actor, rule_id)
    uow.automation.delete(actor.household_id, rule_id)
    operation = change_log.record(
        uow,
        actor,
        "automation.delete",
        f"Regla «{rule.name}» borrada",
        [Change(Entity.AUTOMATION, str(rule_id), "definition", rule.definition(), None)],
        now,
    )
    uow.commit()
    return operation.id if operation else None


# --------------------------------------------------------------------------- aplicar a lo existente


@dataclass(frozen=True, slots=True)
class Proposed:
    transaction: Transaction
    changes: list[Change]
    """Qué cambiaría: campo, antes y después."""


def _view(t: Transaction) -> RowView:
    return RowView(
        description=t.description,
        merchant=t.merchant,
        amount=t.amount,
        kind=t.kind,
        account_id=str(t.account_id),
        bank_type=t.bank_type,
    )


def _targets(uow: UnitOfWork, actor: Actor, rule: AutomationRule) -> list[Transaction]:
    """Los movimientos a los que la regla puede llegar: según su ámbito y lo que se ve."""
    accounts = visible_accounts(uow, actor)
    if rule.scope == HOUSEHOLD_SCOPE:
        ids = [a.id for a in accounts]
    else:
        ids = [
            a.id for a in accounts if a.kind is AccountKind.PERSONAL and a.owner_id == actor.user_id
        ]
    out: list[Transaction] = []
    for account_id in ids:
        out.extend(uow.transactions.for_account(actor.household_id, account_id))
    return sorted(out, key=lambda t: (t.booked_at, str(t.id)))


def _changes_for(
    uow: UnitOfWork, actor: Actor, t: Transaction, decision: Decision, tags: tuple[str, ...]
) -> list[Change]:
    entity_id = str(t.id)
    out: list[Change] = []
    kind = decision.kind or t.kind
    if decision.kind and decision.kind is not t.kind:
        out.append(Change(Entity.TRANSACTION, entity_id, "kind", t.kind.value, decision.kind.value))
        if t.category_id is not None and decision.kind is not TransactionKind.EXPENSE:
            out.append(
                Change(Entity.TRANSACTION, entity_id, "category_id", str(t.category_id), None)
            )
    if (
        decision.category_id
        and kind is TransactionKind.EXPENSE
        and decision.category_id != t.category_id
    ):
        out.append(
            Change(Entity.TRANSACTION, entity_id, "category_id", None, str(decision.category_id))
        )
    if decision.note is not None and decision.note != t.note:
        out.append(Change(Entity.TRANSACTION, entity_id, "note", t.note, decision.note))
    if decision.merchant is not None and decision.merchant != t.merchant:
        out.append(Change(Entity.TRANSACTION, entity_id, "merchant", t.merchant, decision.merchant))
    if decision.tags:
        merged = {x.casefold(): x for x in (*tags, *decision.tags)}
        new = tuple(merged[k] for k in sorted(merged))
        if new != tags:
            out.append(
                Change(
                    Entity.TRANSACTION, entity_id, "tags", join_tags(tags) or None, join_tags(new)
                )
            )
    return out


def propose(uow: UnitOfWork, actor: Actor, rule: AutomationRule) -> list[Proposed]:
    """Qué cambiaría la regla en lo que ya hay. No escribe nada.

    No toca lo revisado ni lo dividido. Una categoría, una nota o un tipo ya fijados no se pisan
    (el tipo solo si es un gasto o un ingreso genérico).
    """
    targets = _targets(uow, actor, rule)
    ids = [t.id for t in targets]
    tags = uow.tags.for_transactions(actor.household_id, ids)
    splits = uow.splits.for_transactions(actor.household_id, ids)
    out: list[Proposed] = []
    for t in targets:
        if t.reviewed or t.id in splits:
            continue
        fixed = Fixed(
            category=t.category_id is not None or t.kind is not TransactionKind.EXPENSE,
            kind=t.kind not in GENERIC_KINDS,
            note=bool(t.note),
        )
        decision = decide([replace(rule, enabled=True)], _view(t), fixed)
        changes = _changes_for(uow, actor, t, decision, tags.get(t.id, ()))
        if changes:
            out.append(Proposed(t, changes))
    return out


def preview_rule(
    uow: UnitOfWork, actor: Actor, draft: RuleDraft | UUID
) -> tuple[int, list[Proposed]]:
    """Cuántos movimientos cambiaría y los primeros 100. Acepta un borrador o una regla guardada."""
    if isinstance(draft, UUID):
        rule = _own(uow, actor, draft)
    else:
        rule = _build(uow, actor, replace(draft, enabled=True), uuid4(), 10)
    found = propose(uow, actor, rule)
    return len(found), found[:PREVIEW_LIMIT]


def apply_rule(
    uow: UnitOfWork, actor: Actor, rule_id: UUID, now: datetime
) -> tuple[int, UUID | None]:
    """Aplica la regla a lo existente: una sola operación que se deshace de una vez."""
    rule = _own(uow, actor, rule_id)
    found = propose(uow, actor, rule)
    all_changes: list[Change] = []
    for p in found:
        t = p.transaction
        values = {c.field: c.after for c in p.changes if c.field != "tags"}
        if values:
            uow.transactions.save(change_log.with_state(t, values))
        for c in p.changes:
            if c.field == "tags":
                uow.tags.set(actor.household_id, t.id, split_tags(str(c.after)))
        all_changes.extend(p.changes)
    operation = change_log.record(
        uow, actor, "automation.apply", f"Regla «{rule.name}» aplicada", all_changes, now
    )
    uow.commit()
    return len(found), operation.id if operation else None
