"""Registro de cambios: qué se corrigió, quién, cuándo, y cómo deshacerlo (ADR-0017)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from openfinance.domain.shared.ids import UserId, WorkspaceId

Value = str | bool | None
"""Valor de un campo tal como se guarda en el registro (JSON): texto, sí/no o nada."""


class Entity(StrEnum):
    TRANSACTION = "transaction"
    RULE = "rule"
    """Regla «comercio → categoría». Su identificador es ``ámbito|comercio``."""
    IMPORT = "import"
    AUTOMATION = "automation"
    """Regla con condiciones (OF-1101). Campo ``definition``: su texto canónico, o ``None`` si no
    existe. Su identificador es el de la regla."""
    CSV_PROFILE = "csv_profile"
    """Perfil de CSV (OF-1105). Campo ``definition`` como en las reglas."""
    SCHEDULE = "schedule"
    """Pago programado (OF-1201). Campo ``definition`` como en las reglas."""
    RATE = "rate"
    """Tipo de cambio (OF-1008). Su identificador es «MONEDA|AAAA-MM-DD»; campo ``rate``: el valor
    como texto o ``None`` si no existe."""
    ATTACHMENT = "attachment"
    """Adjunto de un movimiento (OF-1007). Campo ``present``: ``True`` si está, ``False`` si se
    ha borrado (el archivo se conserva 30 días por si se deshace)."""
    LINK = "link"
    """Traspaso enlazado (OF-1004). Su identificador es el del lado con menor identificador;
    campo ``peer`` = identificador del otro lado, o ``None`` si no hay enlace."""
    SPLIT = "split"
    """Partes de un movimiento dividido (OF-1003). Su identificador es el del movimiento; campo
    ``parts`` = «importe@categoría|…» o ``None`` si no está dividido."""
    MERCHANT = "merchant"
    """Comercio con nombre propio (OF-1001). Campos: ``name`` y ``keys`` (variantes con «|»);
    ``None`` en ``name`` significa que el comercio no existe."""


TRANSACTION_FIELDS = ("kind", "member_id", "category_id", "note", "voided", "reviewed", "merchant")
"""Campos corregibles de un movimiento. El importe, la fecha y el concepto nunca cambian."""


@dataclass(frozen=True, slots=True)
class Change:
    entity: Entity
    entity_id: str
    field: str
    before: Value
    after: Value

    @property
    def key(self) -> tuple[Entity, str, str]:
        return self.entity, self.entity_id, self.field

    def inverse(self) -> Change:
        return Change(self.entity, self.entity_id, self.field, self.after, self.before)


@dataclass(frozen=True, slots=True)
class Operation:
    """Una acción de una persona: uno o varios cambios que se deshacen juntos."""

    id: UUID
    household_id: WorkspaceId
    actor_id: UserId
    created_at: datetime
    action: str
    summary: str
    changes: tuple[Change, ...]
    undone_at: datetime | None = None
    undone_by: UserId | None = None

    @property
    def is_undone(self) -> bool:
        return self.undone_at is not None


def diff(
    entity: Entity, entity_id: str, before: Mapping[str, Value], after: Mapping[str, Value]
) -> list[Change]:
    """Los cambios entre dos estados, solo de los campos que difieren."""
    return [
        Change(entity, entity_id, field, before.get(field), after.get(field))
        for field in after
        if before.get(field) != after.get(field)
    ]


def rule_entity_id(scope: str, merchant: str) -> str:
    return f"{scope}|{merchant}"


def split_rule_entity_id(entity_id: str) -> tuple[str, str]:
    scope, _, merchant = entity_id.partition("|")
    return scope, merchant


def touched(changes: Sequence[Change]) -> set[tuple[Entity, str]]:
    return {(c.entity, c.entity_id) for c in changes}
