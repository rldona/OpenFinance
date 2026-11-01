"""traspasos enlazados entre cuentas propias (OF-1004)

Revision ID: 0012_transaction_links
Revises: 0011_transaction_splits
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_transaction_links"
down_revision: str | None = "0011_transaction_splits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transaction_links",
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("peer_id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("transaction_id <> peer_id", name=op.f("ck_transaction_links_not_self")),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_transaction_links_household_id_households"),
        ),
        sa.ForeignKeyConstraint(
            ["peer_id"],
            ["transactions.id"],
            name=op.f("fk_transaction_links_peer_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_transaction_links_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("transaction_id", name=op.f("pk_transaction_links")),
    )


def downgrade() -> None:
    op.drop_table("transaction_links")
