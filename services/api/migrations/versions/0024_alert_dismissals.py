"""avisos descartados (OF-1301)

Revision ID: 0024_alert_dismissals
Revises: 0023_goal_contributions
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_alert_dismissals"
down_revision: str | None = "0023_goal_contributions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_dismissals",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_alert_dismissals_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", "key", name=op.f("pk_alert_dismissals")),
    )


def downgrade() -> None:
    op.drop_table("alert_dismissals")
