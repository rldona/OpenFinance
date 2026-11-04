"""Flujo de caja mensual del dinero líquido (ADR-0025, OF-1502).

Cada movimiento cae en una sola casilla, así que ingresos más aportaciones menos gasto menos
ahorro más traspasos es exactamente la variación del saldo del mes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from openfinance.domain.insights import Month
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Currency, Money

DEFAULT_MONTHS = 12
MAX_MONTHS = 36


@dataclass(frozen=True, slots=True)
class MonthFlow:
    month: Month
    income: Money
    contributions: Money
    """Neto: lo que entra a la conjunta menos lo que sale de una cuenta personal."""
    spending: Money
    """Gasto neto de devoluciones, en positivo."""
    savings: Money
    """Lo movido al ahorro neto de lo que se saca, en positivo."""
    transfers: Money
    """Traspasos entre cuentas propias, netos."""
    end_balance: Money
    is_partial: bool = False

    @property
    def change(self) -> Money:
        return self.income + self.contributions - self.spending - self.savings + self.transfers


def flow_of(
    transactions: Iterable[Transaction], currency: Currency
) -> tuple[Money, Money, Money, Money, Money]:
    """(ingresos, aportaciones, gasto, ahorro, traspasos) de los movimientos activos."""
    income = contributions = spending = savings = transfers = Money.zero(currency)
    for t in transactions:
        if t.voided:
            continue
        match t.kind:
            case TransactionKind.INCOME:
                income = income + t.amount
            case TransactionKind.CONTRIBUTION:
                contributions = contributions + t.amount
            case TransactionKind.EXPENSE:
                spending = spending - t.amount
            case TransactionKind.SAVINGS_TRANSFER:
                savings = savings - t.amount
            case TransactionKind.INTERNAL_TRANSFER:
                transfers = transfers + t.amount
    return income, contributions, spending, savings, transfers
