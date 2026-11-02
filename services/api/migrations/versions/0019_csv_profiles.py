"""perfiles de CSV para importar el extracto de cualquier banco (OF-1105)

Revision ID: 0019_csv_profiles
Revises: 0018_automation_rules
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_csv_profiles"
down_revision: str | None = "0018_automation_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "csv_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("config", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_csv_profiles_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_csv_profiles_household_id_households"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_csv_profiles")),
    )
    op.create_index("ix_csv_profiles_household", "csv_profiles", ["household_id"])
    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.add_column(sa.Column("profile_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.drop_column("profile_id")
    op.drop_index("ix_csv_profiles_household", table_name="csv_profiles")
    op.drop_table("csv_profiles")
