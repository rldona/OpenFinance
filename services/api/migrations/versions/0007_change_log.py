"""registro de cambios (ADR-0017): operaciones, cambios, nota y anulación de movimientos

Revision ID: 0007_change_log
Revises: 0006_member_patterns
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_change_log"
down_revision: str | None = "0006_member_patterns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "change_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.String(length=200), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["household_id", "actor_id"],
            ["memberships.household_id", "memberships.user_id"],
            name="fk_change_operations_actor_membership",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_change_operations_household_id_households"),
        ),
        sa.ForeignKeyConstraint(
            ["undone_by"], ["users.id"], name=op.f("fk_change_operations_undone_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_operations")),
    )
    with op.batch_alter_table("change_operations", schema=None) as batch_op:
        batch_op.create_index(
            "ix_change_operations_household_actor",
            ["household_id", "actor_id", "created_at"],
            unique=False,
        )

    op.create_table(
        "change_entries",
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.String(length=150), nullable=False),
        sa.Column("field", sa.String(length=30), nullable=False),
        sa.Column("before", sa.String(length=600), nullable=False),
        sa.Column("after", sa.String(length=600), nullable=False),
        sa.CheckConstraint(
            "entity IN ('transaction', 'rule', 'import')",
            name=op.f("ck_change_entries_entity_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["change_operations.id"],
            name=op.f("fk_change_entries_operation_id_change_operations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("operation_id", "position", name=op.f("pk_change_entries")),
    )
    with op.batch_alter_table("change_entries", schema=None) as batch_op:
        batch_op.create_index("ix_change_entries_entity", ["entity", "entity_id"], unique=False)

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("note", sa.String(length=500), server_default="", nullable=False)
        )
        batch_op.add_column(
            sa.Column("voided", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_column("voided")
        batch_op.drop_column("note")

    with op.batch_alter_table("change_entries", schema=None) as batch_op:
        batch_op.drop_index("ix_change_entries_entity")

    op.drop_table("change_entries")
    with op.batch_alter_table("change_operations", schema=None) as batch_op:
        batch_op.drop_index("ix_change_operations_household_actor")

    op.drop_table("change_operations")
