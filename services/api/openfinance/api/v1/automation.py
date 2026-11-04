"""Reglas con condiciones, acciones y fases (ADR-0020, OF-1101 y OF-1102)."""

from uuid import UUID

from fastapi import APIRouter, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    AutomationRuleChangeOut,
    AutomationRuleIn,
    AutomationRuleOut,
    OperationRefOut,
    ProposedChangeOut,
    ProposedOut,
    RuleApplyOut,
    RulePreviewOut,
    TransactionOut,
)
from openfinance.application import automation
from openfinance.application.decorate import decorate
from openfinance.domain.automation import sort_key
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["automation"])


def _draft(body: AutomationRuleIn) -> automation.RuleDraft:
    return automation.RuleDraft(
        name=body.name,
        personal=body.personal,
        phase=body.phase,
        priority=body.priority,
        enabled=body.enabled,
        conditions=[c.model_dump() for c in body.conditions],
        actions=[a.model_dump() for a in body.actions],
    )


@router.get("/automation-rules", response_model=list[AutomationRuleOut])
def list_rules(actor: ActorDep, uow: UowDep) -> list[AutomationRuleOut]:
    """Las reglas del hogar y las tuyas, en el orden en que se evalúan."""
    rules = sorted(automation.visible_rules(uow, actor), key=sort_key)
    return [AutomationRuleOut.of(r) for r in rules]


@router.post(
    "/automation-rules", response_model=AutomationRuleChangeOut, status_code=status.HTTP_201_CREATED
)
def create_rule(body: AutomationRuleIn, actor: ActorDep, uow: UowDep) -> AutomationRuleChangeOut:
    rule, operation_id = automation.create_rule(uow, actor, _draft(body), utc_now())
    return AutomationRuleChangeOut(rule=AutomationRuleOut.of(rule), operation_id=operation_id)


@router.put("/automation-rules/{rule_id}", response_model=AutomationRuleChangeOut)
def update_rule(
    rule_id: UUID, body: AutomationRuleIn, actor: ActorDep, uow: UowDep
) -> AutomationRuleChangeOut:
    rule, operation_id = automation.update_rule(uow, actor, rule_id, _draft(body), utc_now())
    return AutomationRuleChangeOut(rule=AutomationRuleOut.of(rule), operation_id=operation_id)


@router.delete("/automation-rules/{rule_id}", response_model=OperationRefOut)
def delete_rule(rule_id: UUID, actor: ActorDep, uow: UowDep) -> OperationRefOut:
    return OperationRefOut(operation_id=automation.delete_rule(uow, actor, rule_id, utc_now()))


def _preview(uow: UowDep, actor: ActorDep, draft: automation.RuleDraft | UUID) -> RulePreviewOut:
    count, items = automation.preview_rule(uow, actor, draft)
    decor = decorate(uow, actor, [p.transaction for p in items])
    return RulePreviewOut(
        count=count,
        items=[
            ProposedOut(
                transaction=TransactionOut.of(p.transaction, decor),
                changes=[
                    ProposedChangeOut(field=c.field, before=c.before, after=c.after)
                    for c in p.changes
                ],
            )
            for p in items
        ],
    )


@router.post("/automation-rules/preview", response_model=RulePreviewOut)
def preview_draft(body: AutomationRuleIn, actor: ActorDep, uow: UowDep) -> RulePreviewOut:
    """Prueba una regla sin guardarla: qué movimientos cambiaría. No escribe nada."""
    return _preview(uow, actor, _draft(body))


@router.post("/automation-rules/{rule_id}/preview", response_model=RulePreviewOut)
def preview_saved(rule_id: UUID, actor: ActorDep, uow: UowDep) -> RulePreviewOut:
    return _preview(uow, actor, rule_id)


@router.post("/automation-rules/{rule_id}/apply", response_model=RuleApplyOut)
def apply_rule(rule_id: UUID, actor: ActorDep, uow: UowDep) -> RuleApplyOut:
    """Aplica la regla a lo que ya hay, en una sola operación que se deshace de una vez."""
    changed, operation_id = automation.apply_rule(uow, actor, rule_id, utc_now())
    return RuleApplyOut(changed=changed, operation_id=operation_id)
