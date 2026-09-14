from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Chunk, Document
from app.models.enums import DocumentStatus
from app.retrieval.embedding import EmbeddingProvider
from app.retrieval.parents import expand_parent_hits
from app.retrieval.types import RetrievalHit


async def vector_search(
    session: AsyncSession,
    embedding_provider: EmbeddingProvider,
    query: str,
    *,
    top_k: int,
) -> list[RetrievalHit]:
    """使用 pgvector 余弦距离查询，并复用 chunks 上的 HNSW 索引。"""
    query_vector = await embedding_provider.embed_text(query)
    distance = Chunk.embedding.cosine_distance(query_vector)
    statement = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.content,
            Chunk.page_number,
            Chunk.heading_path,
            Document.filename,
            (1 - distance).label("score"),
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Document.status == DocumentStatus.READY,
            Chunk.embedding.is_not(None),
            Chunk.is_parent.is_(False),
        )
        .order_by(distance)
        .limit(top_k)
    )
    rows = (await session.execute(statement)).mappings().all()
    hits = [
        RetrievalHit(
            chunk_id=cast(UUID, row["id"]),
            document_id=cast(UUID, row["document_id"]),
            content=cast(str, row["content"]),
            document_name=cast(str, row["filename"]),
            page_number=cast(int | None, row["page_number"]),
            heading_path=tuple(cast(list[str], row["heading_path"])),
            score=float(row["score"]),
            sources=("vector",),
        )
        for row in rows
    ]
    return await expand_parent_hits(session, hits)
