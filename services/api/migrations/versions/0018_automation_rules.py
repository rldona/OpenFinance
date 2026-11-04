"""reglas con condiciones, acciones y fases (OF-1101)

Revision ID: 0018_automation_rules
Revises: 0017_change_values_text
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_automation_rules"
down_revision: str | None = "0017_change_values_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = (
    "entity IN ('transaction', 'rule', 'import', 'merchant', 'tag', 'split', 'link', "
    "'account', 'attachment', 'reconciliation', 'rate')"
)
_AFTER = (
    "entity IN ('transaction', 'rule', 'import', 'merchant', 'tag', 'split', 'link', "
    "'account', 'attachment', 'reconciliation', 'rate', 'automation', 'csv_profile')"
)


def upgrade() -> None:
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=36), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("phase", sa.String(length=10), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("conditions", sa.Text(), nullable=False),
        sa.Column("actions", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "phase IN ('before', 'normal', 'after')", name=op.f("ck_automation_rules_phase_valid")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_automation_rules_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_automation_rules_household_id_households"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automation_rules")),
    )
    op.create_index("ix_automation_rules_household", "automation_rules", ["household_id"])
    with op.batch_alter_table("change_entries") as batch_op:
        batch_op.drop_constraint(op.f("ck_change_entries_entity_valid"), type_="check")
        batch_op.create_check_constraint(op.f("ck_change_entries_entity_valid"), _AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM change_entries WHERE entity IN ('automation', 'csv_profile')")
    with op.batch_alter_table("change_entries") as batch_op:
        batch_op.drop_constraint(op.f("ck_change_entries_entity_valid"), type_="check")
        batch_op.create_check_constraint(op.f("ck_change_entries_entity_valid"), _BEFORE)
    op.drop_index("ix_automation_rules_household", table_name="automation_rules")
    op.drop_table("automation_rules")
