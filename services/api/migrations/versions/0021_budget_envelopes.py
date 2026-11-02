"""presupuestos con límites o sobres e importes por mes (OF-1203)

Revision ID: 0021_budget_envelopes
Revises: 0020_scheduled_payments
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_budget_envelopes"
down_revision: str | None = "0020_scheduled_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("budgets") as batch_op:
        batch_op.add_column(
            sa.Column("mode", sa.String(length=10), server_default="limit", nullable=False)
        )
        batch_op.add_column(sa.Column("started", sa.String(length=7), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_budgets_mode_valid"), "mode IN ('limit', 'envelope')"
        )
    op.create_table(
        "budget_overrides",
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_budget_overrides_amount_positive")),
        sa.ForeignKeyConstraint(
            ["household_id", "category_id"],
            ["budgets.household_id", "budgets.category_id"],
            name="fk_budget_overrides_budget",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "household_id", "category_id", "month", name=op.f("pk_budget_overrides")
        ),
    )


def downgrade() -> None:
    op.drop_table("budget_overrides")
    with op.batch_alter_table("budgets") as batch_op:
        batch_op.drop_constraint(op.f("ck_budgets_mode_valid"), type_="check")
        batch_op.drop_column("started")
        batch_op.drop_column("mode")
