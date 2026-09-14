from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedBlock:
    """解析器输出的结构块，页码和标题路径在解析阶段确定。"""

    text: str
    page_number: int | None
    heading_path: tuple[str, ...]


@dataclass(frozen=True)
class ChunkDraft:
    """等待写入 chunks 表的切片，chunk_index 在切片阶段稳定生成。"""

    content: str
    chunk_index: int
    page_number: int | None
    heading_path: tuple[str, ...]
