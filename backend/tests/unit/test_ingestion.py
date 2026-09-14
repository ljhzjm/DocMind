from pathlib import Path

import pymupdf
from app.ingestion.chunking import StructureAwareChunker
from app.ingestion.parsers import parse_document
from app.ingestion.types import ParsedBlock


def test_pdf_chunks_keep_every_source_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "manual.pdf"
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    first_page = document.new_page()
    first_page.insert_text((72, 72), "Page one content")
    second_page = document.new_page()
    second_page.insert_text((72, 72), "Page two content")
    document.save(pdf_path)  # type: ignore[no-untyped-call]
    document.close()  # type: ignore[no-untyped-call]

    chunks = StructureAwareChunker(chunk_size=512, chunk_overlap=64).split(parse_document(pdf_path))

    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert all(chunk.heading_path == () for chunk in chunks)


def test_markdown_chunks_preserve_heading_hierarchy(tmp_path: Path) -> None:
    markdown_path = tmp_path / "guide.md"
    markdown_path.write_text(
        """
# Guide
Introduction.
## Install
Install steps.
### Notes
Important note.
## FAQ
Answer.
""".strip(),
        encoding="utf-8",
    )

    chunks = StructureAwareChunker(chunk_size=512, chunk_overlap=64).split(
        parse_document(markdown_path)
    )

    assert [chunk.heading_path for chunk in chunks] == [
        ("Guide",),
        ("Guide", "Install"),
        ("Guide", "Install", "Notes"),
        ("Guide", "FAQ"),
    ]


def test_recursive_fallback_never_exceeds_chunk_size() -> None:
    paragraph = "这句话用于验证递归切片不会超过配置上限。" * 80
    parsed_blocks = [
        ParsedBlock(
            text=paragraph,
            page_number=None,
            heading_path=("Long section",),
        )
    ]

    chunks = StructureAwareChunker(chunk_size=512, chunk_overlap=64).split(parsed_blocks)

    assert len(chunks) > 1
    assert max(len(chunk.content) for chunk in chunks) <= 512
    assert all(chunk.heading_path == ("Long section",) for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
