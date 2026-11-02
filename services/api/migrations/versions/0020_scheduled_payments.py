"""pagos programados (OF-1201)

Revision ID: 0020_scheduled_payments
Revises: 0019_csv_profiles
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_scheduled_payments"
down_revision: str | None = "0019_csv_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = (
    "entity IN ('transaction', 'rule', 'import', 'merchant', 'tag', 'split', 'link', "
    "'account', 'attachment', 'reconciliation', 'rate', 'automation', 'csv_profile')"
)
_AFTER = (
    "entity IN ('transaction', 'rule', 'import', 'merchant', 'tag', 'split', 'link', "
    "'account', 'attachment', 'reconciliation', 'rate', 'automation', 'csv_profile', 'schedule')"
)


def upgrade() -> None:
    op.create_table(
        "scheduled_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("frequency", sa.String(length=10), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("first_due", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("merchant", sa.String(length=120), server_default="", nullable=False),
        sa.Column("variable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount <> 0", name=op.f("ck_scheduled_payments_amount_not_zero")),
        sa.CheckConstraint("interval >= 1", name=op.f("ck_scheduled_payments_interval_positive")),
        sa.CheckConstraint(
            "frequency IN ('once', 'weekly', 'monthly', 'yearly')",
            name=op.f("ck_scheduled_payments_frequency_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "household_id"],
            ["accounts.id", "accounts.household_id"],
            name="fk_scheduled_payments_account_household",
        ),
        sa.ForeignKeyConstraint(
            ["category_id", "household_id"],
            ["categories.id", "categories.household_id"],
            name="fk_scheduled_payments_category_household",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_scheduled_payments_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_scheduled_payments_household_id_households"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduled_payments")),
    )
    op.create_index("ix_scheduled_payments_household", "scheduled_payments", ["household_id"])
    with op.batch_alter_table("change_entries") as batch_op:
        batch_op.drop_constraint(op.f("ck_change_entries_entity_valid"), type_="check")
        batch_op.create_check_constraint(op.f("ck_change_entries_entity_valid"), _AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM change_entries WHERE entity = 'schedule'")
    with op.batch_alter_table("change_entries") as batch_op:
        batch_op.drop_constraint(op.f("ck_change_entries_entity_valid"), type_="check")
        batch_op.create_check_constraint(op.f("ck_change_entries_entity_valid"), _BEFORE)
    op.drop_index("ix_scheduled_payments_household", table_name="scheduled_payments")
    op.drop_table("scheduled_payments")
