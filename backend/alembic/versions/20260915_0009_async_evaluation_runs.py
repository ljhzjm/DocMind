"""add async execution state to evaluation runs

Revision ID: 20260915_0009
Revises: 20260914_0008
Create Date: 2026-09-15 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0009"
down_revision: str | None = "20260914_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 已有记录是同步执行的完整结果，因此直接标记为 completed。
    op.add_column(
        "evaluation_runs",
        sa.Column("task_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "progress_completed",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "progress_total",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE evaluation_runs
        SET status = 'completed',
            completed_at = created_at
        """
    )
    op.create_check_constraint(
        "ck_evaluation_runs_status",
        "evaluation_runs",
        "status IN ('queued', 'running', 'completed', 'failed')",
    )
    op.create_check_constraint(
        "ck_evaluation_runs_progress_completed_non_negative",
        "evaluation_runs",
        "progress_completed >= 0",
    )
    op.create_check_constraint(
        "ck_evaluation_runs_progress_total_non_negative",
        "evaluation_runs",
        "progress_total >= 0",
    )
    op.create_index(
        "ix_evaluation_runs_status_created_at",
        "evaluation_runs",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_status_created_at", table_name="evaluation_runs")
    op.drop_constraint(
        "ck_evaluation_runs_progress_total_non_negative",
        "evaluation_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_evaluation_runs_progress_completed_non_negative",
        "evaluation_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_evaluation_runs_status",
        "evaluation_runs",
        type_="check",
    )
    op.drop_column("evaluation_runs", "completed_at")
    op.drop_column("evaluation_runs", "started_at")
    op.drop_column("evaluation_runs", "error_message")
    op.drop_column("evaluation_runs", "progress_total")
    op.drop_column("evaluation_runs", "progress_completed")
    op.drop_column("evaluation_runs", "status")
    op.drop_column("evaluation_runs", "task_id")
