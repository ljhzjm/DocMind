"""文档上传、解析、结构感知切片与入库服务。"""

from app.ingestion.chunking import StructureAwareChunker
from app.ingestion.types import ChunkDraft, ParsedBlock

__all__ = [
    "ChunkDraft",
    "ParsedBlock",
    "StructureAwareChunker",
]
