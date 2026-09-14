from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeBaseRevision(Base):
    """单行知识库版本，用于答案缓存失效和评测数据版本追踪。"""

    __tablename__ = "knowledge_base_revision"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    revision: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
