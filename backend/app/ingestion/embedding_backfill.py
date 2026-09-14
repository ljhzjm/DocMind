from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.llm.base import LLMError
from app.models.document import Chunk
from app.models.enums import DocumentStatus
from app.repositories.documents import get_document
from app.repositories.knowledge_base import bump_knowledge_base_revision
from app.retrieval.embedding import EmbeddingError, LLMGatewayEmbeddingProvider


class EmbeddingBackfillError(RuntimeError):
    """已有切片的 embedding 回填失败。"""


async def backfill_document_embeddings(
    session: AsyncSession,
    document_id: UUID,
    settings: Settings | None = None,
) -> int:
    """为没有向量的切片批量生成 embedding，并更新知识库 revision。"""
    active_settings = settings or get_settings()
    document = await get_document(session, document_id)
    if document is None:
        raise LookupError(str(document_id))

    document.status = DocumentStatus.PARSING
    await session.commit()
    provider = LLMGatewayEmbeddingProvider()
    try:
        chunks = list(
            (
                await session.scalars(
                    select(Chunk)
                    .where(
                        Chunk.document_id == document_id,
                        Chunk.embedding.is_(None),
                    )
                    .order_by(Chunk.chunk_index)
                )
            ).all()
        )
        for index in range(0, len(chunks), active_settings.embedding_batch_size):
            batch = chunks[index : index + active_settings.embedding_batch_size]
            embeddings = await provider.embed_texts([chunk.content for chunk in batch])
            for chunk, embedding in zip(batch, embeddings, strict=True):
                chunk.embedding = embedding

        if chunks:
            await bump_knowledge_base_revision(session)
        document.status = DocumentStatus.READY
        await session.commit()
        return len(chunks)
    except (LLMError, EmbeddingError, SQLAlchemyError) as exc:
        await session.rollback()
        failed_document = await get_document(session, document_id)
        if failed_document is not None:
            failed_document.status = DocumentStatus.FAILED
            await session.commit()
        raise EmbeddingBackfillError(str(document_id)) from exc
