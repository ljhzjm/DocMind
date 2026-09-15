"""add immutable evaluation dataset versions

Revision ID: 20260915_0011
Revises: 20260915_0010
Create Date: 2026-09-15 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0011"
down_revision: str | None = "20260915_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_dataset_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "case_count >= 0",
            name="ck_eval_dataset_versions_case_count_non_negative",
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_eval_dataset_versions_revision_positive",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_eval_dataset_versions"),
        sa.UniqueConstraint(
            "dataset_name",
            "content_hash",
            name="uq_eval_dataset_versions_name_hash",
        ),
        sa.UniqueConstraint(
            "dataset_name",
            "revision",
            name="uq_eval_dataset_versions_name_revision",
        ),
    )
    op.create_index(
        "ix_eval_dataset_versions_name_revision",
        "eval_dataset_versions",
        ["dataset_name", "revision"],
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("dataset_revision", sa.Integer(), nullable=True),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "knowledge_base_revision",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "dataset_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_evaluation_runs_dataset_version_id_eval_dataset_versions",
        "evaluation_runs",
        "eval_dataset_versions",
        ["dataset_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_evaluation_runs_dataset_version_id_eval_dataset_versions",
        "evaluation_runs",
        type_="foreignkey",
    )
    op.drop_column("evaluation_runs", "dataset_snapshot")
    op.drop_column("evaluation_runs", "knowledge_base_revision")
    op.drop_column("evaluation_runs", "dataset_revision")
    op.drop_column("evaluation_runs", "dataset_version_id")
    op.drop_index(
        "ix_eval_dataset_versions_name_revision",
        table_name="eval_dataset_versions",
    )
    op.drop_table("eval_dataset_versions")
