"""add content_type_tags

Revision ID: 4f5dc2929a19
Revises: fa194da18ea1
Create Date: 2026-05-06 10:16:33.306930

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f5dc2929a19"
down_revision: str | Sequence[str] | None = "fa194da18ea1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_type_tags",
        sa.Column("tag_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mention_id", sa.String(length=128), nullable=False),
        sa.Column(
            "content_type",
            sa.Enum(
                "review", "deal", "other", name="contenttype", native_enum=False, length=16
            ),
            nullable=False,
        ),
        sa.Column("classifier_confidence", sa.Float(), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mention_id"], ["mentions.mention_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tag_id"),
        sa.UniqueConstraint("mention_id", "prompt_version", name="uq_content_type_tags_key"),
    )
    with op.batch_alter_table("content_type_tags", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_content_type_tags_mention_id"), ["mention_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("content_type_tags", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_content_type_tags_mention_id"))

    op.drop_table("content_type_tags")
