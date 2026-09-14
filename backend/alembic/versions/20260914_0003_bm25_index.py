"""add BM25 inverted index

Revision ID: 20260914_0003
Revises: 20260914_0002
Create Date: 2026-09-14 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914_0003"
down_revision: str | None = "20260914_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # chunk_terms 将 term -> chunk_id 的倒排 posting 展开为行，term_frequency 为 tf。
    # 联合主键 (term, chunk_id) 支持按 term 快速取 posting list，且天然去重。
    # chunk_id 单独建索引用于删除切片、重算文档长度和批量清理词项。
    op.create_table(
        "chunk_terms",
        sa.Column("term", sa.String(length=128), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("term_frequency", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "term_frequency > 0",
            name="ck_chunk_terms_frequency_positive",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name="fk_chunk_terms_chunk_id_chunks",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("term", "chunk_id", name="pk_chunk_terms"),
    )
    op.create_index(
        "ix_chunk_terms_chunk_id",
        "chunk_terms",
        ["chunk_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("chunk_terms")
