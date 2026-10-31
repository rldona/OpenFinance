"""El hogar (workspace) y quién pertenece a él."""

from __future__ import annotations

from dataclasses import dataclass

from openfinance.domain.shared import Currency
from openfinance.domain.shared.ids import UserId, WorkspaceId


@dataclass(frozen=True, slots=True)
class Household:
    id: WorkspaceId
    name: str
    currency: Currency

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("El hogar necesita un nombre")


@dataclass(frozen=True, slots=True)
class Actor:
    """Quién hace la petición y en qué hogar. Toda lectura y escritura parte de aquí."""

    user_id: UserId
    household_id: WorkspaceId
