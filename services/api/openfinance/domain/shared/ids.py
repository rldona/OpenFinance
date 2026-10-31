"""Identificadores tipados. Evitan mezclar, por ejemplo, un UserId con un WorkspaceId."""

from typing import NewType
from uuid import UUID

UserId = NewType("UserId", UUID)
WorkspaceId = NewType("WorkspaceId", UUID)
"""Identificador del hogar: el workspace es la frontera de datos (ADR-0002, ADR-0012)."""
AccountId = NewType("AccountId", UUID)
TransactionId = NewType("TransactionId", UUID)
