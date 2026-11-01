"""ideas de ahorro descartadas por el hogar (OF-806)

Revision ID: 0008_dismissed_ideas
Revises: 0007_change_log
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_dismissed_ideas"
down_revision: str | None = "0007_change_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dismissed_ideas",
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("idea_id", sa.String(length=60), nullable=False),
        sa.Column("dismissed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "dismissed_by"],
            ["memberships.household_id", "memberships.user_id"],
            name="fk_dismissed_ideas_member_membership",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_dismissed_ideas_household_id_households"),
        ),
        sa.PrimaryKeyConstraint("household_id", "idea_id", name=op.f("pk_dismissed_ideas")),
    )


def downgrade() -> None:
    op.drop_table("dismissed_ideas")
