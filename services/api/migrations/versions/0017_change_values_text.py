"""los valores del registro de cambios ya no caben en 600 caracteres (notas de 2000)

Revision ID: 0017_change_values_text
Revises: 0016_exchange_rates
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_change_values_text"
down_revision: str | None = "0016_exchange_rates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Una nota de 2000 caracteres, escrita como JSON, supera con creces los 600 anteriores.
    with op.batch_alter_table("change_entries") as batch_op:
        for column in ("before", "after"):
            batch_op.alter_column(
                column,
                existing_type=sa.String(length=600),
                type_=sa.Text(),
                existing_nullable=False,
            )


def downgrade() -> None:
    with op.batch_alter_table("change_entries") as batch_op:
        for column in ("before", "after"):
            batch_op.alter_column(
                column,
                existing_type=sa.Text(),
                type_=sa.String(length=600),
                existing_nullable=False,
            )
