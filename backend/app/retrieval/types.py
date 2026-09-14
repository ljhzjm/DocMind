from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class SearchMode(StrEnum):
    VECTOR = "vector"
    BM25 = "bm25"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class RetrievalHit:
    """检索统一结果，sources 用于区分向量、BM25 或融合命中。"""

    chunk_id: UUID
    document_id: UUID
    content: str
    document_name: str
    page_number: int | None
    heading_path: tuple[str, ...]
    score: float
    sources: tuple[str, ...]
