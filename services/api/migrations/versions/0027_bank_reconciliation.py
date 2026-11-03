"""conciliación automática con el banco (OF-1404)

Revision ID: 0027_bank_reconciliation
Revises: 0026_bank_connections
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_bank_reconciliation"
down_revision: str | None = "0026_bank_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("bank_ref", sa.String(length=64), nullable=True))
    op.create_index("ix_transactions_account_bank_ref", "transactions", ["account_id", "bank_ref"])
    op.add_column("bank_links", sa.Column("balance_difference", sa.Numeric(19, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("bank_links", "balance_difference")
    op.drop_index("ix_transactions_account_bank_ref", table_name="transactions")
    op.drop_column("transactions", "bank_ref")
