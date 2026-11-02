"""tipos de cuenta: efectivo, tarjeta, préstamo e inversión (OF-1005)

Revision ID: 0013_account_types
Revises: 0012_transaction_links
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_account_types"
down_revision: str | None = "0012_transaction_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Las cuentas que ya existen son de banco: no cambia nada de lo que ya funcionaba.
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(
            sa.Column("type", sa.String(length=20), nullable=False, server_default="bank")
        )
        batch_op.create_check_constraint(
            op.f("ck_accounts_type_valid"),
            "type IN ('bank', 'cash', 'card', 'loan', 'investment')",
        )


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_constraint(op.f("ck_accounts_type_valid"), type_="check")
        batch_op.drop_column("type")
