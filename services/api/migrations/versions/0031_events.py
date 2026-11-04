"""eventos y viajes que agrupan gastos compartidos (OF-1603)

Revision ID: 0031_events
Revises: 0030_shared_expenses
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_events"
down_revision: str | None = "0030_shared_expenses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("icon", sa.String(length=8), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("closed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"], ["households.id"], name=op.f("fk_events_household_id_households")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index("ix_events_household", "events", ["household_id"])
    with op.batch_alter_table("shared_expenses") as batch:
        batch.add_column(sa.Column("event_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_shared_expenses_event_id_events"), "events", ["event_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("shared_expenses") as batch:
        batch.drop_constraint(op.f("fk_shared_expenses_event_id_events"), type_="foreignkey")
        batch.drop_column("event_id")
    op.drop_index("ix_events_household", table_name="events")
    op.drop_table("events")
