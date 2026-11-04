"""movimientos divididos en partes con categoría (OF-1003)

Revision ID: 0011_transaction_splits
Revises: 0010_tags_and_long_notes
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_transaction_splits"
down_revision: str | None = "0010_tags_and_long_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transaction_splits",
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("amount <> 0", name=op.f("ck_transaction_splits_amount_not_zero")),
        sa.ForeignKeyConstraint(
            ["category_id", "household_id"],
            ["categories.id", "categories.household_id"],
            name="fk_transaction_splits_category_household",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_transaction_splits_household_id_households"),
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_transaction_splits_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("transaction_id", "position", name=op.f("pk_transaction_splits")),
    )


def downgrade() -> None:
    op.drop_table("transaction_splits")
