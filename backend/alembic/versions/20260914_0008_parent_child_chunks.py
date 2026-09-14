"""add parent-child chunk marker

Revision ID: 20260914_0008
Revises: 20260914_0007
Create Date: 2026-09-14 22:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0008"
down_revision: str | None = "20260914_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "is_parent",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_chunks_is_parent",
        "chunks",
        ["is_parent"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_is_parent", table_name="chunks")
    op.drop_column("chunks", "is_parent")
