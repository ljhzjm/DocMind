"""add rerank usage step

Revision ID: 20260914_0005
Revises: 20260914_0004
Create Date: 2026-09-14 21:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260914_0005"
down_revision: str | None = "20260914_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE usage_step ADD VALUE IF NOT EXISTS 'rerank' BEFORE 'generate'")


def downgrade() -> None:
    # PostgreSQL 不支持安全删除 enum value，保留类型值以兼容已产生的历史数据。
    pass
