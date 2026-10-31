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
    RuleOut,
    TransactionOut,
)
from openfinance.application import categories
from openfinance.domain.categories import CategoryId, merchant_label
from openfinance.domain.shared.ids import TransactionId
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
    """Pone o quita la categoría de un gasto y, por defecto, aprende la regla."""
    result = categories.categorize_transaction(
        uow,
        actor,
        TransactionId(transaction_id),
        CategoryId(body.category_id) if body.category_id else None,
        utc_now(),
        learn=body.learn,
    )
    rule = (
        RuleOut(merchant=merchant_label(result.rule.merchant), category_id=result.rule.category_id)
        if result.rule
        else None
    )
    return CategorizeOut(
        transaction=TransactionOut.of(result.transaction),
        rule=rule,
        also_categorized=result.also_categorized,
    )
