"""roles de las personas del hogar e invitaciones (OF-1601)

Revision ID: 0029_roles_and_invitations
Revises: 0028_saved_reports
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_roles_and_invitations"
down_revision: str | None = "0028_saved_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("memberships") as batch:
        batch.add_column(
            sa.Column("role", sa.String(length=10), server_default="owner", nullable=False)
        )
        batch.create_check_constraint(
            op.f("ck_memberships_role_valid"), "role IN ('owner', 'editor', 'viewer')"
        )
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"], ["households.id"], name=op.f("fk_invitations_household_id_households")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_invitations_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invitations_token_hash")),
    )
    op.create_index("ix_invitations_household", "invitations", ["household_id"])


def downgrade() -> None:
    op.drop_index("ix_invitations_household", table_name="invitations")
    op.drop_table("invitations")
    with op.batch_alter_table("memberships") as batch:
        batch.drop_constraint(op.f("ck_memberships_role_valid"), type_="check")
        batch.drop_column("role")
