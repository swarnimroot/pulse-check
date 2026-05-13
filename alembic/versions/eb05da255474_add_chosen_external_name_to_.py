"""add chosen_external_name to deliberation_tags

Revision ID: eb05da255474
Revises: b8560c93bbd8
Create Date: 2026-05-13 14:00:00.000000

Adds the v2 ``chosen_external_name`` column to ``deliberation_tags`` so the
classifier can record the OP's chosen winner when it is an untracked external
product. Mutually exclusive with ``chosen_product_id``: at most one is set
per row. Nullable; existing rows back-fill as NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eb05da255474"
down_revision: str | Sequence[str] | None = "b8560c93bbd8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("deliberation_tags", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("chosen_external_name", sa.String(256), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("deliberation_tags", schema=None) as batch_op:
        batch_op.drop_column("chosen_external_name")
