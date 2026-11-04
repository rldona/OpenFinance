"""movimientos revisados y comprobación del saldo contra el banco (OF-1006)

Revision ID: 0014_reconciliation
Revises: 0013_account_types
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_reconciliation"
down_revision: str | None = "0013_account_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.create_table(
        "reconciliations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("bank_balance", sa.Numeric(19, 4), nullable=False),
        sa.Column("computed_balance", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "household_id"],
            ["accounts.id", "accounts.household_id"],
            name="fk_reconciliations_account_household",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_reconciliations_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_reconciliations_household_id_households"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliations")),
    )
    op.create_index("ix_reconciliations_account", "reconciliations", ["account_id", "as_of"])


def downgrade() -> None:
    op.drop_index("ix_reconciliations_account", table_name="reconciliations")
    op.drop_table("reconciliations")
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("reviewed")
