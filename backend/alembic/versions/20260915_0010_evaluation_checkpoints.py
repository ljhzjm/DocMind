"""add cancellation and resume checkpoints

Revision ID: 20260915_0010
Revises: 20260915_0009
Create Date: 2026-09-15 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0010"
down_revision: str | None = "20260915_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_evaluation_runs_status",
        "evaluation_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evaluation_runs_status",
        "evaluation_runs",
        "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
    )
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "attempt",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "checkpoint",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "checkpoint")
    op.drop_column("evaluation_runs", "attempt")
    op.drop_constraint(
        "ck_evaluation_runs_status",
        "evaluation_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evaluation_runs_status",
        "evaluation_runs",
        "status IN ('queued', 'running', 'completed', 'failed')",
    )
