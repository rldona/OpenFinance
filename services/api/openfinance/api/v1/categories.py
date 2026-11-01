from typing import Literal
from uuid import UUID

from fastapi import APIRouter, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import (
    CategorizeIn,
    CategorizeOut,
    CategoryIn,
    CategoryOut,
    CategoryPatch,
    CountOut,
    OperationRefOut,
    RuleOut,
    RuleViewOut,
    TransactionOut,
)
from openfinance.application import categories, merchants
from openfinance.domain.categories import CategoryId, merchant_label
from openfinance.domain.shared.ids import TransactionId, UserId
from openfinance.infrastructure.time import utc_now

router = APIRouter(tags=["categories"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(actor: ActorDep, uow: UowDep) -> list[CategoryOut]:
    return [CategoryOut.of(c) for c in categories.list_categories(uow, actor)]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, actor: ActorDep, uow: UowDep) -> CategoryOut:
    return CategoryOut.of(categories.create_category(uow, actor, body.name, body.icon, body.color))


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: UUID, body: CategoryPatch, actor: ActorDep, uow: UowDep
) -> CategoryOut:
    """Renombrar, cambiar icono o color, u ocultar. Las categorías no se borran."""
    return CategoryOut.of(
        categories.update_category(
            uow,
            actor,
            CategoryId(category_id),
            name=body.name,
            icon=body.icon,
            color=body.color,
            hidden=body.hidden,
        )
    )


@router.get("/transactions/uncategorized-count", response_model=CountOut)
def uncategorized_count(actor: ActorDep, uow: UowDep) -> CountOut:
    return CountOut(count=categories.uncategorized_count(uow, actor))


@router.patch("/transactions/{transaction_id}", response_model=CategorizeOut)
def categorize(
    transaction_id: UUID, body: CategorizeIn, actor: ActorDep, uow: UowDep
) -> CategorizeOut:
    """Corrige un movimiento: categoría (y, por defecto, aprende la regla), tipo, persona o nota.

    Solo cambia lo que se envía. Todo queda en el registro de cambios y se puede deshacer.
    """
    sent = body.model_fields_set
    edit = categories.TransactionEdit(
        kind=body.kind,
        member_id=UserId(body.member_id) if body.member_id else None,
        note=body.note,
        set_category="category_id" in sent,
        category_id=CategoryId(body.category_id) if body.category_id else None,
        learn=body.learn,
    )
    result = categories.edit_transaction(uow, actor, TransactionId(transaction_id), edit, utc_now())
    rule = (
        RuleOut(merchant=merchant_label(result.rule.merchant), category_id=result.rule.category_id)
        if result.rule
        else None
    )
    return CategorizeOut(
        transaction=TransactionOut.of(
            result.transaction, merchants.names_for(uow, actor.household_id, [result.transaction])
        ),
        rule=rule,
        also_categorized=result.also_categorized,
        operation_id=result.operation_id,
    )


@router.get("/rules", response_model=list[RuleViewOut])
def list_rules(actor: ActorDep, uow: UowDep) -> list[RuleViewOut]:
    """Reglas «comercio → categoría» del hogar y tus personales (nunca las de la pareja)."""
    return [
        RuleViewOut(
            key=v.rule.merchant,
            merchant=merchant_label(v.rule.merchant),
            category_id=v.rule.category_id,
            scope="personal" if v.personal else "household",
            matches=v.matches,
        )
        for v in categories.list_rules(uow, actor)
    ]


@router.delete("/rules/{scope}/{merchant}", response_model=OperationRefOut)
def delete_rule(
    scope: Literal["household", "personal"], merchant: str, actor: ActorDep, uow: UowDep
) -> OperationRefOut:
    """Borra una regla. Los movimientos ya clasificados no cambian; se puede deshacer."""
    op = categories.delete_rule(uow, actor, scope == "personal", merchant, utc_now())
    return OperationRefOut(operation_id=op)
