"""add evaluation dataset

Revision ID: 20260914_0004
Revises: 20260914_0003
Create Date: 2026-09-14 20:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914_0004"
down_revision: str | None = "20260914_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # expected_chunk_ids 直接存 UUID 数组，便于逐题计算 Recall@K 和 MRR。
    # tags 使用 GIN 索引支持按难例、领域等标签筛选数据集。
    op.create_table(
        "eval_dataset",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=False),
        sa.Column(
            "expected_chunk_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String(length=128)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_eval_dataset"),
    )
    op.create_index(
        "ix_eval_dataset_name_created_at",
        "eval_dataset",
        ["dataset_name", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_eval_dataset_tags_gin",
        "eval_dataset",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("eval_dataset")
