"""plantillas de movimientos (OF-1204)

Revision ID: 0022_transaction_templates
Revises: 0021_budget_envelopes
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_transaction_templates"
down_revision: str | None = "0021_budget_envelopes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = (
    "entity IN ('transaction', 'rule', 'import', 'merchant', 'tag', 'split', 'link', "
    "'account', 'attachment', 'reconciliation', 'rate', 'automation', 'csv_profile', 'schedule')"
)
_AFTER = (
    "entity IN ('transaction', 'rule', 'import', 'merchant', 'tag', 'split', 'link', "
    "'account', 'attachment', 'reconciliation', 'rate', 'automation', 'csv_profile', 'schedule', "
    "'template')"
)


def upgrade() -> None:
    op.create_table(
        "transaction_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=36), server_default="", nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_transaction_templates_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_transaction_templates_household_id_households"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transaction_templates")),
    )
    op.create_index("ix_transaction_templates_household", "transaction_templates", ["household_id"])
    with op.batch_alter_table("change_entries") as batch_op:
        batch_op.drop_constraint(op.f("ck_change_entries_entity_valid"), type_="check")
        batch_op.create_check_constraint(op.f("ck_change_entries_entity_valid"), _AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM change_entries WHERE entity = 'template'")
    with op.batch_alter_table("change_entries") as batch_op:
        batch_op.drop_constraint(op.f("ck_change_entries_entity_valid"), type_="check")
        batch_op.create_check_constraint(op.f("ck_change_entries_entity_valid"), _BEFORE)
    op.drop_index("ix_transaction_templates_household", table_name="transaction_templates")
    op.drop_table("transaction_templates")
