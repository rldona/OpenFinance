"""conexión con el banco (OF-1401)

Revision ID: 0026_bank_connections
Revises: 0025_push_notifications
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_bank_connections"
down_revision: str | None = "0025_push_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("aspsp", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=64), server_default="", nullable=False),
        sa.Column("session_id", sa.String(length=200), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_bank_connections_household_id_households"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_bank_connections_owner_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_connections")),
    )
    op.create_index("ix_bank_connections_owner", "bank_connections", ["household_id", "owner_id"])
    op.create_table(
        "bank_links",
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("remote_uid", sa.String(length=200), nullable=False),
        sa.Column("iban_tail", sa.String(length=4), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("bank_balance", sa.Numeric(19, 4), nullable=True),
        sa.Column("bank_balance_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_bank_links_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["bank_connections.id"],
            name=op.f("fk_bank_links_connection_id_bank_connections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("connection_id", "remote_uid", name=op.f("pk_bank_links")),
    )


def downgrade() -> None:
    op.drop_table("bank_links")
    op.drop_index("ix_bank_connections_owner", table_name="bank_connections")
    op.drop_table("bank_connections")
