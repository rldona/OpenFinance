"""etiquetas de movimientos y notas de hasta 2000 caracteres (OF-1002)

Revision ID: 0010_tags_and_long_notes
Revises: 0009_merchants
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_tags_and_long_notes"
down_revision: str | None = "0009_merchants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.alter_column(
            "note",
            existing_type=sa.String(length=500),
            type_=sa.String(length=2000),
            existing_nullable=False,
            existing_server_default="",
        )
    op.create_table(
        "transaction_tags",
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("tag_key", sa.String(length=40), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_transaction_tags_household_id_households"),
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_transaction_tags_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("transaction_id", "tag_key", name=op.f("pk_transaction_tags")),
    )
    op.create_index(
        "ix_transaction_tags_household_key", "transaction_tags", ["household_id", "tag_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_tags_household_key", table_name="transaction_tags")
    op.drop_table("transaction_tags")
    # Las notas más largas de 500 se recortan al volver atrás.
    op.execute("UPDATE transactions SET note = substr(note, 1, 500) WHERE length(note) > 500")
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.alter_column(
            "note",
            existing_type=sa.String(length=2000),
            type_=sa.String(length=500),
            existing_nullable=False,
            existing_server_default="",
        )
