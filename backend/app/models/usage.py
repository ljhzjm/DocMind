import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import UsageStep, enum_values


class UsageRecord(Base):
    """按 trace 与步骤记录模型成本，供成本面板和离线评测聚合。"""

    __tablename__ = "usage_records"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0", name="ck_usage_input_tokens_non_negative"),
        CheckConstraint("output_tokens >= 0", name="ck_usage_output_tokens_non_negative"),
        CheckConstraint("latency_ms >= 0", name="ck_usage_latency_non_negative"),
        Index("ix_usage_records_trace_id", "trace_id"),
        Index("ix_usage_records_step_created_at", "step", "created_at"),
        Index("ix_usage_records_model_created_at", "model", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    step: Mapped[UsageStep] = mapped_column(
        Enum(
            UsageStep,
            name="usage_step",
            values_callable=enum_values,
            native_enum=True,
        ),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
