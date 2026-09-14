from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ingestion.types import ChunkDraft
from app.models.document import Chunk, Document
from app.models.enums import DocumentStatus


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
    session.add_all(
        [
            Chunk(
                document_id=document.id,
                content=draft.content,
                chunk_index=draft.chunk_index,
                page_number=draft.page_number,
                heading_path=list(draft.heading_path),
                parent_chunk_id=None,
                embedding=None,
            )
            for draft in drafts
        ]
    )
    document.chunk_count = len(drafts)
    return len(drafts)
