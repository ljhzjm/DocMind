from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ingestion.types import ChunkDraft
from app.models.chunk_term import ChunkTerm
from app.models.document import Chunk, Document
from app.models.enums import DocumentStatus
from app.retrieval.tokenization import term_frequencies


async def create_document(session: AsyncSession, document: Document) -> Document:
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def get_document(session: AsyncSession, document_id: UUID) -> Document | None:
    return await session.get(Document, document_id)


async def set_document_status(
    session: AsyncSession,
    document: Document,
    status: DocumentStatus,
) -> None:
    document.status = status
    await session.commit()


def get_document_sync(session: Session, document_id: UUID) -> Document | None:
    return session.get(Document, document_id)


def set_document_status_sync(
    session: Session,
    document: Document,
    status: DocumentStatus,
) -> None:
    document.status = status
    session.commit()


def replace_chunks(
    session: Session,
    document: Document,
    drafts: Sequence[ChunkDraft],
) -> int:
    """幂等替换文档切片，重新解析不会留下旧版本数据。"""
    session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    chunks = [
        Chunk(
            document_id=document.id,
            content=draft.content,
            chunk_index=draft.chunk_index,
            page_number=draft.page_number,
            heading_path=list(draft.heading_path),
            parent_chunk_id=None,
            embedding=(list(draft.embedding) if draft.embedding is not None else None),
            is_parent=draft.is_parent,
        )
        for draft in drafts
    ]
    session.add_all(chunks)
    session.flush()

    for chunk, draft in zip(chunks, drafts, strict=True):
        if draft.parent_index is not None:
            chunk.parent_chunk_id = chunks[draft.parent_index].id

    # BM25 倒排索引与切片在同一事务写入；删除旧 chunks 时数据库级联清理旧 postings。
    for chunk, draft in zip(chunks, drafts, strict=True):
        if draft.is_parent:
            continue
        session.add_all(
            [
                ChunkTerm(
                    term=term,
                    chunk_id=chunk.id,
                    term_frequency=frequency,
                )
                for term, frequency in term_frequencies(chunk.content).items()
            ]
        )

    leaf_chunk_count = sum(1 for draft in drafts if not draft.is_parent)
    document.chunk_count = leaf_chunk_count
    return leaf_chunk_count


async def list_documents(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[Document]:
    result = await session.scalars(
        select(Document).order_by(Document.created_at.desc()).limit(limit)
    )
    return list(result.all())


async def list_document_chunks(
    session: AsyncSession,
    document_id: UUID,
) -> list[Chunk]:
    result = await session.scalars(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
    )
    return list(result.all())
