import asyncio
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pymupdf
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ingestion.chunking import StructureAwareChunker
from app.ingestion.parsers import UnsupportedDocumentTypeError, parse_document
from app.ingestion.types import ChunkDraft
from app.llm.base import LLMError
from app.models.enums import DocumentStatus
from app.repositories.documents import (
    get_document_sync,
    replace_chunks,
    set_document_status_sync,
)
from app.repositories.knowledge_base import bump_knowledge_base_revision_sync
from app.retrieval.embedding import EmbeddingError, LLMGatewayEmbeddingProvider


class DocumentNotFoundError(LookupError):
    """后台任务引用的文档不存在。"""


class DocumentIngestionError(RuntimeError):
    """文档解析、切片或入库失败。"""


def ingest_document(
    session: Session,
    document_id: UUID,
    settings: Settings,
) -> int:
    """解析文件、结构切片并原子替换 chunks，最终更新文档状态。"""
    document = get_document_sync(session, document_id)
    if document is None:
        raise DocumentNotFoundError(str(document_id))

    set_document_status_sync(session, document, DocumentStatus.PARSING)
    source_path = settings.upload_dir / f"{document.id}.{document.file_type}"

    try:
        blocks = parse_document(
            Path(source_path),
            ocr_enabled=settings.ocr_enabled,
            ocr_language=settings.ocr_language,
        )
        drafts = StructureAwareChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            parent_child_enabled=settings.parent_child_enabled,
            parent_chunk_size=settings.parent_chunk_size,
        ).split(blocks)
        embedded_drafts = _embed_drafts(drafts, settings)
        replace_chunks(session, document, embedded_drafts)
        bump_knowledge_base_revision_sync(session)
        document.status = DocumentStatus.READY
        session.commit()
        return len(drafts)
    except (
        OSError,
        UnicodeDecodeError,
        UnsupportedDocumentTypeError,
        pymupdf.FileDataError,
        LLMError,
        EmbeddingError,
        ValueError,
        SQLAlchemyError,
    ) as exc:
        session.rollback()
        failed_document = get_document_sync(session, document_id)
        if failed_document is not None:
            set_document_status_sync(
                session,
                failed_document,
                DocumentStatus.FAILED,
            )
        raise DocumentIngestionError(str(document_id)) from exc


def _embed_drafts(
    drafts: Sequence[ChunkDraft],
    settings: Settings,
) -> list[ChunkDraft]:
    if not drafts:
        return []
    embeddable_drafts = [draft for draft in drafts if not draft.is_parent]
    if not embeddable_drafts:
        return list(drafts)
    provider = LLMGatewayEmbeddingProvider()
    embeddings = asyncio.run(
        _embed_texts_in_batches(
            provider,
            [draft.content for draft in embeddable_drafts],
            batch_size=settings.embedding_batch_size,
        )
    )
    embedded_by_index = {
        draft.chunk_index: tuple(embedding)
        for draft, embedding in zip(embeddable_drafts, embeddings, strict=True)
    }
    return [replace(draft, embedding=embedded_by_index.get(draft.chunk_index)) for draft in drafts]


async def _embed_texts_in_batches(
    provider: LLMGatewayEmbeddingProvider,
    texts: Sequence[str],
    *,
    batch_size: int,
) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for index in range(0, len(texts), batch_size):
        embeddings.extend(await provider.embed_texts(list(texts[index : index + batch_size])))
    return embeddings
