"""tipos de cambio manuales para varias monedas (OF-1008)

Revision ID: 0016_exchange_rates
Revises: 0015_attachments
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_exchange_rates"
down_revision: str | None = "0015_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exchange_rates",
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(24, 8), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False, server_default="manual"),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("rate > 0", name=op.f("ck_exchange_rates_rate_positive")),
        sa.CheckConstraint(
            "source IN ('manual', 'extracto')", name=op.f("ck_exchange_rates_source_valid")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_exchange_rates_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_exchange_rates_household_id_households"),
        ),
        sa.PrimaryKeyConstraint(
            "household_id", "currency", "on_date", name=op.f("pk_exchange_rates")
        ),
    )


def downgrade() -> None:
    op.drop_table("exchange_rates")
