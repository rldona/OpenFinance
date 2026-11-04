"""comercios con nombre propio y variantes del banco (OF-1001)

Revision ID: 0009_merchants
Revises: 0008_dismissed_ideas
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_merchants"
down_revision: str | None = "0008_dismissed_ideas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OLD_ENTITIES = "entity IN ('transaction', 'rule', 'import')"
_NEW_ENTITIES = (
    "entity IN ('transaction', 'rule', 'import', 'merchant', 'tag', 'split', 'link', "
    "'account', 'attachment', 'reconciliation', 'rate')"
)


def upgrade() -> None:
    # El registro de cambios admite las entidades de la fase 10 (comercios, etiquetas, partes…).
    with op.batch_alter_table("change_entries") as batch_op:
        batch_op.drop_constraint(op.f("ck_change_entries_entity_valid"), type_="check")
        batch_op.create_check_constraint(op.f("ck_change_entries_entity_valid"), _NEW_ENTITIES)
    op.create_table(
        "merchants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["household_id"], ["households.id"], name=op.f("fk_merchants_household_id_households")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchants")),
        sa.UniqueConstraint("id", "household_id", name="uq_merchants_id_household"),
    )
    op.create_table(
        "merchant_keys",
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_merchant_keys_household_id_households"),
        ),
        sa.ForeignKeyConstraint(
            ["merchant_id", "household_id"],
            ["merchants.id", "merchants.household_id"],
            name="fk_merchant_keys_merchant_household",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("household_id", "key", name=op.f("pk_merchant_keys")),
    )
    op.create_index("ix_merchant_keys_merchant", "merchant_keys", ["merchant_id"])


def downgrade() -> None:
    op.execute("DELETE FROM change_entries WHERE entity NOT IN ('transaction', 'rule', 'import')")
    with op.batch_alter_table("change_entries") as batch_op:
        batch_op.drop_constraint(op.f("ck_change_entries_entity_valid"), type_="check")
        batch_op.create_check_constraint(op.f("ck_change_entries_entity_valid"), _OLD_ENTITIES)
    op.drop_index("ix_merchant_keys_merchant", table_name="merchant_keys")
    op.drop_table("merchant_keys")
    op.drop_table("merchants")
