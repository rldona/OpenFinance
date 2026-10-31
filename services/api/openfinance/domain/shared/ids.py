"""Identificadores tipados. Evitan mezclar, por ejemplo, un UserId con un WorkspaceId."""

from typing import NewType
from uuid import UUID

UserId = NewType("UserId", UUID)
WorkspaceId = NewType("WorkspaceId", UUID)
AccountId = NewType("AccountId", UUID)
TransactionId = NewType("TransactionId", UUID)
