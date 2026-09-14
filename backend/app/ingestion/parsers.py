from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from app.ingestion.types import ParsedBlock

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_SUPPORTED_EXTENSIONS = frozenset({".pdf", ".md", ".markdown"})


class UnsupportedDocumentTypeError(ValueError):
    """上传扩展名不属于解析器支持范围。"""


def parse_document(path: Path) -> list[ParsedBlock]:
    """按扩展名选择解析器，并返回带结构元数据的文本块。"""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix in {".md", ".markdown"}:
        return parse_markdown(path)
    if suffix not in _SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentTypeError(f"unsupported document type: {suffix}")
    raise UnsupportedDocumentTypeError(f"unsupported document type: {suffix}")


def parse_pdf(path: Path) -> list[ParsedBlock]:
    """逐页提取 PDF 文本，页码固定使用从 1 开始的物理页号。"""
    blocks: list[ParsedBlock] = []
    with pymupdf.open(path) as document:  # type: ignore[no-untyped-call]
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            if text:
                blocks.append(
                    ParsedBlock(
                        text=text,
                        page_number=page_number,
                        heading_path=(),
                    )
                )
    return blocks


def parse_markdown(path: Path) -> list[ParsedBlock]:
    """按 ATX 标题维护层级栈，并输出各标题段落的 heading_path。"""
    blocks: list[ParsedBlock] = []
    heading_stack: list[tuple[int, str]] = []
    buffer: list[str] = []
    in_code_fence = False

    def flush() -> None:
        text = "\n".join(buffer).strip()
        buffer.clear()
        if text:
            blocks.append(
                ParsedBlock(
                    text=text,
                    page_number=None,
                    heading_path=tuple(title for _, title in heading_stack),
                )
            )

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence
            buffer.append(line)
            continue

        match = None if in_code_fence else _HEADING_PATTERN.match(line)
        if match is None:
            buffer.append(line)
            continue

        flush()
        level = len(match.group(1))
        title = match.group(2).strip()
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, title))

    flush()
    return blocks
