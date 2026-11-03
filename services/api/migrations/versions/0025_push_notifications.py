"""notificaciones Web Push (OF-1302)

Revision ID: 0025_push_notifications
Revises: 0024_alert_dismissals
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_push_notifications"
down_revision: str | None = "0024_alert_dismissals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_push_subscriptions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint("endpoint", name=op.f("uq_push_subscriptions_endpoint")),
    )
    op.create_index("ix_push_subscriptions_user", "push_subscriptions", ["user_id"])
    op.create_table(
        "notification_prefs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kinds", sa.String(length=200), server_default="", nullable=False),
        sa.Column("weekly", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notification_prefs_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_notification_prefs")),
    )
    op.create_table(
        "alert_deliveries",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_alert_deliveries_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", "key", name=op.f("pk_alert_deliveries")),
    )


def downgrade() -> None:
    op.drop_table("alert_deliveries")
    op.drop_table("notification_prefs")
    op.drop_index("ix_push_subscriptions_user", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
