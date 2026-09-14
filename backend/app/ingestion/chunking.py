from collections.abc import Sequence

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.types import ChunkDraft, ParsedBlock

_DEFAULT_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", ". ", " ", ""]


class StructureAwareChunker:
    """优先保留标题段落，仅对超长结构块执行递归字符切片。"""

    def __init__(
        self,
        *,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        parent_child_enabled: bool = False,
        parent_chunk_size: int = 2048,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be between 0 and chunk_size")

        self._chunk_size = chunk_size
        self._parent_child_enabled = parent_child_enabled
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=_DEFAULT_SEPARATORS,
            keep_separator=True,
        )
        self._parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=parent_chunk_size,
            chunk_overlap=0,
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
            if self._parent_child_enabled and len(text) > self._chunk_size:
                self._append_parent_child_chunks(chunks, block)
            else:
                parts = [text] if len(text) <= self._chunk_size else self._splitter.split_text(text)
                for part in parts:
                    self._append_chunk(
                        chunks,
                        content=part,
                        page_number=block.page_number,
                        heading_path=block.heading_path,
                    )
        return chunks

    def _append_parent_child_chunks(
        self,
        chunks: list[ChunkDraft],
        block: ParsedBlock,
    ) -> None:
        for parent_text in self._parent_splitter.split_text(block.text.strip()):
            parent_content = parent_text.strip()
            if not parent_content:
                continue
            parent_index = len(chunks)
            self._append_chunk(
                chunks,
                content=parent_content,
                page_number=block.page_number,
                heading_path=block.heading_path,
                is_parent=True,
            )
            for child_text in self._splitter.split_text(parent_content):
                self._append_chunk(
                    chunks,
                    content=child_text,
                    page_number=block.page_number,
                    heading_path=block.heading_path,
                    parent_index=parent_index,
                )

    @staticmethod
    def _append_chunk(
        chunks: list[ChunkDraft],
        *,
        content: str,
        page_number: int | None,
        heading_path: tuple[str, ...],
        is_parent: bool = False,
        parent_index: int | None = None,
    ) -> None:
        normalized = content.strip()
        if not normalized:
            return
        chunks.append(
            ChunkDraft(
                content=normalized,
                chunk_index=len(chunks),
                page_number=page_number,
                heading_path=heading_path,
                is_parent=is_parent,
                parent_index=parent_index,
            )
        )
