"""add evaluation runs

Revision ID: 20260914_0007
Revises: 20260914_0006
Create Date: 2026-09-14 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914_0007"
down_revision: str | None = "20260914_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("configs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_runs"),
    )
    op.create_index(
        "ix_evaluation_runs_dataset_created_at",
        "evaluation_runs",
        ["dataset_name", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("evaluation_runs")
