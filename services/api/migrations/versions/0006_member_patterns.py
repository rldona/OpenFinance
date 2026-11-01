"""member patterns

Revision ID: 0006_member_patterns
Revises: 0005_savings
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_member_patterns"
down_revision: str | None = "0005_savings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "member_patterns",
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("pattern", sa.String(length=60), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "direction IN ('inflow', 'outflow')", name=op.f("ck_member_patterns_direction_valid")
        ),
        sa.CheckConstraint(
            "length(pattern) >= 3", name=op.f("ck_member_patterns_pattern_min_length")
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "user_id"],
            ["memberships.household_id", "memberships.user_id"],
            name="fk_member_patterns_member_membership",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_member_patterns_household_id_households"),
        ),
        sa.PrimaryKeyConstraint(
            "household_id", "direction", "pattern", name=op.f("pk_member_patterns")
        ),
    )


def downgrade() -> None:

    op.drop_table("member_patterns")
