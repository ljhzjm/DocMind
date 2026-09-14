import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChunkTerm(Base):
    """BM25 倒排索引：每个词项保存其在切片中的词频。"""

    __tablename__ = "chunk_terms"
    __table_args__ = (
        CheckConstraint(
            "term_frequency > 0",
            name="ck_chunk_terms_frequency_positive",
        ),
        Index("ix_chunk_terms_chunk_id", "chunk_id"),
    )

    term: Mapped[str] = mapped_column(String(128), primary_key=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    term_frequency: Mapped[int] = mapped_column(Integer, nullable=False)
