"""allow chunks to be persisted before embedding

Revision ID: 20260914_0002
Revises: 20260914_0001
Create Date: 2026-09-14 18:00:00
"""

from collections.abc import Sequence

from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260914_0002"
down_revision: str | None = "20260914_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 解析与切片先落库，Embedding 阶段再原子填充向量，避免零向量误入检索。
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=Vector(dim=1024),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=Vector(dim=1024),
        nullable=False,
    )
