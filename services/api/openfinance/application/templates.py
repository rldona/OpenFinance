"""Plantillas de movimientos: guardar, cambiar, borrar y usar (OF-1204).

Una plantilla es del hogar o personal (solo de quien la crea). Una del hogar no puede usar una
cuenta personal (la veríais los dos); una personal solo puede usar cuentas que su dueño ve.
Usarla es un alta manual normal: lleva su registro de cambios y se deshace.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4

from openfinance.application import changes as change_log
from openfinance.application import movements
from openfinance.application import tags as tags_service
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import HOUSEHOLD_SCOPE, CategoryId
from openfinance.domain.changes import Change, Entity
from openfinance.domain.ledger import AccountKind, Transaction, TransactionKind
from openfinance.domain.shared.ids import AccountId
from openfinance.domain.templates import TemplateError, TransactionTemplate, build
from openfinance.domain.workspaces import Actor

MAX_TEMPLATES = 100


@dataclass(frozen=True, slots=True)
class TemplateDraft:
    name: str
    kind: TransactionKind
    amount: str
    description: str
    account_id: UUID
    personal: bool = False
    category_id: UUID | None = None
    tags: tuple[str, ...] = ()
    note: str = ""


def personal_scope(actor: Actor) -> str:
    return str(actor.user_id)


def visible_templates(uow: UnitOfWork, actor: Actor) -> list[TransactionTemplate]:
    """Las del hogar y las personales propias. Las personales de la pareja no existen."""
    scopes = {HOUSEHOLD_SCOPE, personal_scope(actor)}
    return [t for t in uow.templates.for_household(actor.household_id) if t.scope in scopes]


def _own(uow: UnitOfWork, actor: Actor, template_id: UUID) -> TransactionTemplate:
    template = uow.templates.get(actor.household_id, template_id)
    if template is None or template.scope not in (HOUSEHOLD_SCOPE, personal_scope(actor)):
        raise NotFoundError("Plantilla no encontrada")
    return template


def _build(
    uow: UnitOfWork, actor: Actor, draft: TemplateDraft, template_id: UUID, scope: str
) -> TransactionTemplate:
    account = next((a for a in visible_accounts(uow, actor) if a.id == draft.account_id), None)
    if account is None:
        raise NotFoundError("Cuenta no encontrada")
    if scope == HOUSEHOLD_SCOPE and account.kind is AccountKind.PERSONAL:
        raise InvalidRequestError(
            "Una plantilla del hogar no puede usar una cuenta personal: hazla personal"
        )
    category_id: CategoryId | None = None
    if draft.category_id is not None:
        category = uow.categories.get(actor.household_id, CategoryId(draft.category_id))
        if category is None:
            raise NotFoundError("Categoría no encontrada")
        if category.hidden:
            raise InvalidRequestError(f"La categoría «{category.name}» está oculta")
        category_id = category.id
    try:
        return build(
            template_id,
            actor.household_id,
            scope,
            draft.name,
            draft.kind,
            draft.amount,
            draft.description,
            AccountId(account.id),
            category_id,
            list(draft.tags),
            draft.note,
        )
    except TemplateError as exc:
        raise InvalidRequestError(str(exc)) from exc


def _check_name(uow: UnitOfWork, actor: Actor, name: str, own_id: UUID | None) -> None:
    wanted = " ".join(name.split()).casefold()
    if any(t.name.casefold() == wanted and t.id != own_id for t in visible_templates(uow, actor)):
        raise ConflictError("Ya hay una plantilla con ese nombre")


def create_template(
    uow: UnitOfWork, actor: Actor, draft: TemplateDraft, now: datetime
) -> tuple[TransactionTemplate, UUID | None]:
    if len(uow.templates.for_household(actor.household_id)) >= MAX_TEMPLATES:
        raise ConflictError(f"El hogar ya tiene {MAX_TEMPLATES} plantillas")
    _check_name(uow, actor, draft.name, None)
    scope = personal_scope(actor) if draft.personal else HOUSEHOLD_SCOPE
    template = _build(uow, actor, draft, uuid4(), scope)
    uow.templates.save(template, actor.user_id)
    operation = change_log.record(
        uow,
        actor,
        "template.create",
        f"Plantilla «{template.name}» creada",
        [Change(Entity.TEMPLATE, str(template.id), "definition", None, template.definition())],
        now,
    )
    uow.commit()
    return template, operation.id if operation else None


def update_template(
    uow: UnitOfWork, actor: Actor, template_id: UUID, draft: TemplateDraft, now: datetime
) -> tuple[TransactionTemplate, UUID | None]:
    before = _own(uow, actor, template_id)
    _check_name(uow, actor, draft.name, template_id)
    updated = _build(uow, actor, draft, template_id, before.scope)
    if updated.definition() == before.definition():
        return before, None
    uow.templates.save(updated, actor.user_id)
    operation = change_log.record(
        uow,
        actor,
        "template.update",
        f"Plantilla «{updated.name}» cambiada",
        [
            Change(
                Entity.TEMPLATE,
                str(template_id),
                "definition",
                before.definition(),
                updated.definition(),
            )
        ],
        now,
    )
    uow.commit()
    return updated, operation.id if operation else None


def delete_template(uow: UnitOfWork, actor: Actor, template_id: UUID, now: datetime) -> UUID | None:
    template = _own(uow, actor, template_id)
    uow.templates.delete(actor.household_id, template_id)
    operation = change_log.record(
        uow,
        actor,
        "template.delete",
        f"Plantilla «{template.name}» borrada",
        [Change(Entity.TEMPLATE, str(template_id), "definition", template.definition(), None)],
        now,
    )
    uow.commit()
    return operation.id if operation else None


@dataclass(frozen=True, slots=True)
class Used:
    transaction: Transaction
    operation_id: UUID | None


def use_template(
    uow: UnitOfWork, actor: Actor, template_id: UUID, booked_on: date, now: datetime
) -> Used:
    """Crea el movimiento de la plantilla en esa fecha, por el alta manual de siempre.

    Deshacer la operación devuelta anula el movimiento. Las etiquetas se ponen después y quedan
    en su propia operación; si el movimiento se anula, no cuentan en nada.
    """
    template = _own(uow, actor, template_id)
    created = movements.add_manual(
        uow,
        actor,
        movements.NewManual(
            account_id=template.account_id,
            booked_on=booked_on,
            description=template.description,
            amount=str(template.amount),
            kind=template.kind,
            category_id=template.category_id,
            note=template.note,
        ),
        now,
    )
    if template.tags:
        tags_service.set_transaction_tags(
            uow, actor, created.transaction.id, list(template.tags), now
        )
    return Used(created.transaction, created.operation_id)
