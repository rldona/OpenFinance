"""import batches

Revision ID: 0003_imports
Revises: 0002_household_ledger
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_imports"
down_revision: str | None = "0002_household_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "import_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id", "household_id"],
            ["accounts.id", "accounts.household_id"],
            name="fk_import_batches_account_household",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_import_batches_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_import_batches_household_id_households"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
    )
    op.create_index(
        "ix_import_batches_household_created_at",
        "import_batches",
        ["household_id", "created_at"],
        unique=False,
    )
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("import_id", sa.Uuid(), nullable=True))
        batch.create_index(op.f("ix_transactions_import_id"), ["import_id"], unique=False)
        batch.create_foreign_key(
            op.f("fk_transactions_import_id_import_batches"),
            "import_batches",
            ["import_id"],
            ["id"],
        )


def downgrade() -> None:

    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint(op.f("fk_transactions_import_id_import_batches"), type_="foreignkey")
        batch.drop_index(op.f("ix_transactions_import_id"))
        batch.drop_column("import_id")
    op.drop_index("ix_import_batches_household_created_at", table_name="import_batches")
    op.drop_table("import_batches")
