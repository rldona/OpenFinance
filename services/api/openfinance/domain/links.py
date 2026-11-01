"""Traspasos enlazados entre cuentas propias (OF-1004).

Los dos lados de un traspaso («sale de la conjunta» y «entra en la cuenta de ahorro») se
enlazan para que ninguno cuente como gasto ni como ingreso y se vea el par.
"""

from __future__ import annotations

from openfinance.domain.ledger import Transaction, TransactionKind

LINKABLE_TO_TRANSFER = (TransactionKind.EXPENSE, TransactionKind.INCOME)
"""Gastos e ingresos pasan a «entre cuentas» al enlazarse; el resto conserva su tipo."""

WINDOW_DAYS = 7
"""Los dos lados de un traspaso se anotan con pocos días de diferencia."""


class LinkError(ValueError):
    pass


def validate_link(a: Transaction, b: Transaction) -> None:
    if a.id == b.id:
        raise LinkError("Un movimiento no se puede enlazar consigo mismo")
    if a.voided or b.voided:
        raise LinkError("No se pueden enlazar movimientos borrados")
    if a.account_id == b.account_id:
        raise LinkError("Un traspaso va de una cuenta a otra distinta")
    if a.amount.currency != b.amount.currency:
        raise LinkError("Los dos lados del traspaso van en la misma moneda")
    if a.amount + b.amount != a.amount.__class__.zero(a.amount.currency):
        raise LinkError("Los dos lados tienen que ser del mismo importe y de signo contrario")


def pair(a: Transaction, b: Transaction) -> tuple[Transaction, Transaction]:
    """Los dos lados en orden estable (por identificador): el primero da nombre al enlace."""
    return (a, b) if str(a.id) < str(b.id) else (b, a)
