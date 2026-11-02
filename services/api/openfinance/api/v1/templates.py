"""Plantillas de movimientos (OF-1204)."""

from uuid import UUID

from fastapi import APIRouter, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    ManualTransactionOut,
    OperationRefOut,
    TemplateChangeOut,
    TemplateIn,
    TemplateOut,
    TemplateUseIn,
    TransactionOut,
)
from openfinance.application import templates
from openfinance.application.decorate import decorate
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.templates import TransactionTemplate
from openfinance.domain.workspaces import Actor
from openfinance.infrastructure.time import local_today, utc_now

router = APIRouter(tags=["templates"])


def _draft(body: TemplateIn) -> templates.TemplateDraft:
    return templates.TemplateDraft(**body.model_dump(exclude={"tags"}), tags=tuple(body.tags))


def _out(uow: UnitOfWork, actor: Actor, items: list[TransactionTemplate]) -> list[TemplateOut]:
    currency = {a.id: a.currency.code for a in visible_accounts(uow, actor)}
    return [TemplateOut.of(t, currency[t.account_id]) for t in items if t.account_id in currency]


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(actor: ActorDep, uow: UowDep) -> list[TemplateOut]:
    return _out(uow, actor, templates.visible_templates(uow, actor))


@router.post("/templates", response_model=TemplateChangeOut, status_code=status.HTTP_201_CREATED)
def create_template(body: TemplateIn, actor: ActorDep, uow: UowDep) -> TemplateChangeOut:
    template, operation_id = templates.create_template(uow, actor, _draft(body), utc_now())
    return TemplateChangeOut(template=_out(uow, actor, [template])[0], operation_id=operation_id)


@router.put("/templates/{template_id}", response_model=TemplateChangeOut)
def update_template(
    template_id: UUID, body: TemplateIn, actor: ActorDep, uow: UowDep
) -> TemplateChangeOut:
    template, operation_id = templates.update_template(
        uow, actor, template_id, _draft(body), utc_now()
    )
    return TemplateChangeOut(template=_out(uow, actor, [template])[0], operation_id=operation_id)


@router.delete("/templates/{template_id}", response_model=OperationRefOut)
def delete_template(template_id: UUID, actor: ActorDep, uow: UowDep) -> OperationRefOut:
    return OperationRefOut(
        operation_id=templates.delete_template(uow, actor, template_id, utc_now())
    )


@router.post(
    "/templates/{template_id}/use",
    response_model=ManualTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def use_template(
    template_id: UUID, body: TemplateUseIn, actor: ActorDep, uow: UowDep
) -> ManualTransactionOut:
    """Crea el movimiento de la plantilla (hoy, o en la fecha que se indique)."""
    used = templates.use_template(
        uow, actor, template_id, body.booked_on or local_today(), utc_now()
    )
    return ManualTransactionOut(
        transaction=TransactionOut.of(used.transaction, decorate(uow, actor, [used.transaction])),
        operation_id=used.operation_id,
    )
