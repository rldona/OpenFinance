"""Plantillas de movimientos: un movimiento manual guardado para crearlo con un clic (OF-1204).

Una plantilla no es un movimiento: no cuenta en nada hasta que se usa, y usarla pasa por el
flujo normal de altas manuales (con registro de cambios y deshacer).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from openfinance.domain.categories import HOUSEHOLD_SCOPE, CategoryId
from openfinance.domain.ledger import TransactionKind
from openfinance.domain.shared.ids import AccountId, WorkspaceId
from openfinance.domain.tags import TagError, clean_tags

MAX_NAME = 60
MAX_DESCRIPTION = 200
MAX_NOTE = 2000
KINDS = (TransactionKind.EXPENSE, TransactionKind.INCOME)


class TemplateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TransactionTemplate:
    id: UUID
    household_id: WorkspaceId
    scope: str
    """Vacío si es del hogar; el identificador de la persona si es solo suya."""
    name: str
    kind: TransactionKind
    amount: Decimal
    """Siempre positivo: el signo lo da el tipo."""
    description: str
    account_id: AccountId
    category_id: CategoryId | None = None
    tags: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > MAX_NAME:
            raise TemplateError(f"La plantilla necesita un nombre de hasta {MAX_NAME} caracteres")
        if self.kind not in KINDS:
            raise TemplateError("Una plantilla es de un gasto o de un ingreso")
        if self.amount <= 0 or self.amount != self.amount.quantize(Decimal("0.01")):
            raise TemplateError("El importe debe ser mayor que cero y con hasta dos decimales")
        if not self.description.strip() or len(self.description) > MAX_DESCRIPTION:
            raise TemplateError(f"El concepto tiene entre 1 y {MAX_DESCRIPTION} caracteres")
        if len(self.note) > MAX_NOTE:
            raise TemplateError(f"La nota no puede superar {MAX_NOTE} caracteres")
        if self.category_id is not None and self.kind is not TransactionKind.EXPENSE:
            raise TemplateError("Solo los gastos tienen categoría")

    @property
    def personal(self) -> bool:
        return self.scope != HOUSEHOLD_SCOPE

    def definition(self) -> str:
        """El texto canónico (registro de cambios y base de datos)."""
        return json.dumps(
            {
                "name": self.name,
                "kind": self.kind.value,
                "amount": str(self.amount),
                "description": self.description,
                "account_id": str(self.account_id),
                "category_id": str(self.category_id) if self.category_id else None,
                "tags": list(self.tags),
                "note": self.note,
                "scope": self.scope,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )


def build(
    template_id: UUID,
    household_id: WorkspaceId,
    scope: str,
    name: str,
    kind: TransactionKind,
    amount: str,
    description: str,
    account_id: AccountId,
    category_id: CategoryId | None,
    tags: list[str],
    note: str,
) -> TransactionTemplate:
    """Una plantilla validada y normalizada a partir de datos del cliente."""
    try:
        value = Decimal(amount.strip().replace(",", "."))
    except InvalidOperation as exc:
        raise TemplateError("Importe no válido") from exc
    cents = Decimal("0.01")
    if value.is_finite() and value == value.quantize(cents):
        value = value.quantize(cents)  # «2» y «2,00» son el mismo importe
    try:
        cleaned = clean_tags(tags)
    except TagError as exc:
        raise TemplateError(str(exc)) from exc
    return TransactionTemplate(
        id=template_id,
        household_id=household_id,
        scope=scope,
        name=" ".join(name.split()),
        kind=kind,
        amount=value,
        description=" ".join(description.split()),
        account_id=account_id,
        category_id=category_id,
        tags=cleaned,
        note=" ".join(note.split()),
    )


def from_definition(
    template_id: UUID, household_id: WorkspaceId, definition: str
) -> TransactionTemplate:
    data: dict[str, Any] = json.loads(definition)
    return TransactionTemplate(
        id=template_id,
        household_id=household_id,
        scope=data["scope"],
        name=data["name"],
        kind=TransactionKind(data["kind"]),
        amount=Decimal(data["amount"]),
        description=data["description"],
        account_id=AccountId(UUID(data["account_id"])),
        category_id=CategoryId(UUID(data["category_id"])) if data["category_id"] else None,
        tags=tuple(data["tags"]),
        note=data["note"],
    )
