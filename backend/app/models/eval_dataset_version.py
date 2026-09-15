import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvalDatasetVersion(Base):
    """评测数据集的不可变版本，保存完整样本快照。"""

    __tablename__ = "eval_dataset_versions"
    __table_args__ = (
        UniqueConstraint(
            "dataset_name",
            "revision",
            name="uq_eval_dataset_versions_name_revision",
        ),
        UniqueConstraint(
            "dataset_name",
            "content_hash",
            name="uq_eval_dataset_versions_name_hash",
        ),
        CheckConstraint(
            "revision > 0",
            name="ck_eval_dataset_versions_revision_positive",
        ),
        CheckConstraint(
            "case_count >= 0",
            name="ck_eval_dataset_versions_case_count_non_negative",
        ),
        Index(
            "ix_eval_dataset_versions_name_revision",
            "dataset_name",
            "revision",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
