import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RetrievalThreshold(Base):
    """按检索配置保存离线校准得到的拒答阈值。"""

    __tablename__ = "retrieval_thresholds"
    __table_args__ = (
        UniqueConstraint(
            "mode",
            "top_k",
            "rerank_provider",
            name="uq_retrieval_thresholds_configuration",
        ),
        CheckConstraint(
            "top_k > 0",
            name="ck_retrieval_thresholds_top_k_positive",
        ),
        CheckConstraint(
            "sample_count > 0",
            name="ck_retrieval_thresholds_sample_count_positive",
        ),
        Index("ix_retrieval_thresholds_lookup", "mode", "top_k", "rerank_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    rerank_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
