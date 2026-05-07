"""add aggregate_a1 secondary bucket columns

Revision ID: b8560c93bbd8
Revises: 4f5dc2929a19
Create Date: 2026-05-07 13:17:33.060035

Option 3 (session 9): split A1 aggregate into PRIMARY/SECONDARY buckets.
Adds eight `*_secondary` columns mirroring the existing primary columns.
Existing rows get zero/empty defaults; on next ``aggregate_a1`` rerun the
delete-then-insert path repopulates both buckets together.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8560c93bbd8"
down_revision: str | Sequence[str] | None = "4f5dc2929a19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("aggregates_aspect_sku", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "total_mentions_secondary",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "polarity_counts_secondary",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "net_sentiment_secondary",
                sa.Float(),
                nullable=False,
                server_default="0.0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "intensity_counts_secondary",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "verified_share_secondary",
                sa.Float(),
                nullable=False,
                server_default="0.0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "by_source_secondary",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "by_recency_secondary",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "mention_ids_secondary",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("aggregates_aspect_sku", schema=None) as batch_op:
        batch_op.drop_column("mention_ids_secondary")
        batch_op.drop_column("by_recency_secondary")
        batch_op.drop_column("by_source_secondary")
        batch_op.drop_column("verified_share_secondary")
        batch_op.drop_column("intensity_counts_secondary")
        batch_op.drop_column("net_sentiment_secondary")
        batch_op.drop_column("polarity_counts_secondary")
        batch_op.drop_column("total_mentions_secondary")
