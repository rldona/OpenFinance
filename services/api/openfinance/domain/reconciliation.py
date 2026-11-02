"""Conciliación: comprobar el saldo de una cuenta contra el del banco en una fecha (OF-1006)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, UserId, WorkspaceId


@dataclass(frozen=True, slots=True)
class Reconciliation:
    id: UUID
    household_id: WorkspaceId
    account_id: AccountId
    as_of: date
    bank_balance: Money
    """Lo que dice el banco que había ese día."""
    computed_balance: Money
    """Saldo inicial más los movimientos anotados hasta ese día."""
    created_by: UserId
    created_at: datetime

    @property
    def difference(self) -> Money:
        """Lo que falta (positivo) o sobra (negativo) en OpenFinance respecto al banco."""
        return self.bank_balance - self.computed_balance

    @property
    def matches(self) -> bool:
        return self.difference.is_zero
