"""aportaciones y prioridad en los objetivos (OF-1206)

Revision ID: 0023_goal_contributions
Revises: 0022_transaction_templates
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_goal_contributions"
down_revision: str | None = "0022_transaction_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = (
    "entity IN ('transaction', 'rule', 'import', 'merchant', 'tag', 'split', 'link', "
    "'account', 'attachment', 'reconciliation', 'rate', 'automation', 'csv_profile', 'schedule', "
    "'template')"
)
_AFTER = (
    "entity IN ('transaction', 'rule', 'import', 'merchant', 'tag', 'split', 'link', "
    "'account', 'attachment', 'reconciliation', 'rate', 'automation', 'csv_profile', 'schedule', "
    "'template', 'goal_contribution')"
)


def upgrade() -> None:
    with op.batch_alter_table("goals") as batch_op:
        batch_op.add_column(
            sa.Column("priority", sa.Integer(), server_default="50", nullable=False)
        )
    op.create_table(
        "goal_contributions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("made_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("note", sa.String(length=200), server_default="", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount <> 0", name=op.f("ck_goal_contributions_amount_not_zero")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_goal_contributions_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"], ["goals.id"], name="fk_goal_contributions_goal", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_goal_contributions_household_id_households"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goal_contributions")),
    )
    op.create_index("ix_goal_contributions_goal", "goal_contributions", ["goal_id"])
    with op.batch_alter_table("change_entries") as batch_op:
        batch_op.drop_constraint(op.f("ck_change_entries_entity_valid"), type_="check")
        batch_op.create_check_constraint(op.f("ck_change_entries_entity_valid"), _AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM change_entries WHERE entity = 'goal_contribution'")
    with op.batch_alter_table("change_entries") as batch_op:
        batch_op.drop_constraint(op.f("ck_change_entries_entity_valid"), type_="check")
        batch_op.create_check_constraint(op.f("ck_change_entries_entity_valid"), _BEFORE)
    op.drop_index("ix_goal_contributions_goal", table_name="goal_contributions")
    op.drop_table("goal_contributions")
    with op.batch_alter_table("goals") as batch_op:
        batch_op.drop_column("priority")
