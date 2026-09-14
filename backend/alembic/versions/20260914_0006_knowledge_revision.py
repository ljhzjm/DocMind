"""add knowledge base revision

Revision ID: 20260914_0006
Revises: 20260914_0005
Create Date: 2026-09-14 21:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0006"
down_revision: str | None = "20260914_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_base_revision",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "revision",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("revision >= 0", name="ck_knowledge_revision_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_base_revision"),
    )
    op.execute("INSERT INTO knowledge_base_revision (id, revision) VALUES (1, 0)")


def downgrade() -> None:
    op.drop_table("knowledge_base_revision")
