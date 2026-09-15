"""add calibrated retrieval refusal thresholds

Revision ID: 20260915_0012
Revises: 20260915_0011
Create Date: 2026-09-15 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0012"
down_revision: str | None = "20260915_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retrieval_thresholds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("rerank_provider", sa.String(length=50), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sample_count > 0",
            name="ck_retrieval_thresholds_sample_count_positive",
        ),
        sa.CheckConstraint(
            "top_k > 0",
            name="ck_retrieval_thresholds_top_k_positive",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_retrieval_thresholds"),
        sa.UniqueConstraint(
            "mode",
            "top_k",
            "rerank_provider",
            name="uq_retrieval_thresholds_configuration",
        ),
    )
    op.create_index(
        "ix_retrieval_thresholds_lookup",
        "retrieval_thresholds",
        ["mode", "top_k", "rerank_provider"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retrieval_thresholds_lookup",
        table_name="retrieval_thresholds",
    )
    op.drop_table("retrieval_thresholds")
