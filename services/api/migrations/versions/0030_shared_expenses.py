"""reparto de gastos: invitados, gastos compartidos y liquidaciones (OF-1602)

Revision ID: 0030_shared_expenses
Revises: 0029_roles_and_invitations
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_shared_expenses"
down_revision: str | None = "0029_roles_and_invitations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "guests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"], ["households.id"], name=op.f("fk_guests_household_id_households")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guests")),
    )
    op.create_index("ix_guests_household", "guests", ["household_id"])
    op.create_table(
        "shared_expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("method", sa.String(length=12), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voided", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_shared_expenses_household_id_households"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_shared_expenses_category_id_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_shared_expenses_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shared_expenses")),
    )
    op.create_index(
        "ix_shared_expenses_household_on", "shared_expenses", ["household_id", "on_date"]
    )
    for table in ("shared_expense_payers", "shared_expense_parts"):
        op.create_table(
            table,
            sa.Column("expense_id", sa.Uuid(), nullable=False),
            sa.Column("participant_id", sa.Uuid(), nullable=False),
            sa.Column("amount", sa.Numeric(19, 4), nullable=False),
            sa.ForeignKeyConstraint(
                ["expense_id"],
                ["shared_expenses.id"],
                name=op.f(f"fk_{table}_expense_id_shared_expenses"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("expense_id", "participant_id", name=op.f(f"pk_{table}")),
        )
    op.create_table(
        "settlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("from_id", sa.Uuid(), nullable=False),
        sa.Column("to_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["household_id"], ["households.id"], name=op.f("fk_settlements_household_id_households")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_settlements_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"], ["users.id"], name=op.f("fk_settlements_confirmed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settlements")),
        sa.UniqueConstraint(
            "household_id", "reference", name=op.f("uq_settlements_household_reference")
        ),
    )
    op.create_index("ix_settlements_household", "settlements", ["household_id"])


def downgrade() -> None:
    op.drop_index("ix_settlements_household", table_name="settlements")
    op.drop_table("settlements")
    op.drop_table("shared_expense_parts")
    op.drop_table("shared_expense_payers")
    op.drop_index("ix_shared_expenses_household_on", table_name="shared_expenses")
    op.drop_table("shared_expenses")
    op.drop_index("ix_guests_household", table_name="guests")
    op.drop_table("guests")
