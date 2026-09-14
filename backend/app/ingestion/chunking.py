from collections.abc import Sequence

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.types import ChunkDraft, ParsedBlock

_DEFAULT_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", ". ", " ", ""]


class StructureAwareChunker:
    """优先保留标题段落，仅对超长结构块执行递归字符切片。"""

    def __init__(self, *, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be between 0 and chunk_size")

        self._chunk_size = chunk_size
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=_DEFAULT_SEPARATORS,
            keep_separator=True,
        )

    def split(self, blocks: Sequence[ParsedBlock]) -> list[ChunkDraft]:
        """将结构块展平为稳定顺序的切片，并保留页码与标题路径。"""
        chunks: list[ChunkDraft] = []
        for block in blocks:
            text = block.text.strip()
            if not text:
                continue
            parts = [text] if len(text) <= self._chunk_size else self._splitter.split_text(text)
            for part in parts:
                content = part.strip()
                if not content:
                    continue
                chunks.append(
                    ChunkDraft(
                        content=content,
                        chunk_index=len(chunks),
                        page_number=block.page_number,
                        heading_path=block.heading_path,
                    )
                )
        return chunks
