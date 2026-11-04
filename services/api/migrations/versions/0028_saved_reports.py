"""informes a medida guardados (OF-1503)

Revision ID: 0028_saved_reports
Revises: 0027_bank_reconciliation
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_saved_reports"
down_revision: str | None = "0027_bank_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("shared", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_saved_reports_household_id_households"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_saved_reports_owner_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_reports")),
    )
    op.create_index("ix_saved_reports_household", "saved_reports", ["household_id", "owner_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_reports_household", table_name="saved_reports")
    op.drop_table("saved_reports")
