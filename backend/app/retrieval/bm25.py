import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk_term import ChunkTerm
from app.models.document import Chunk, Document
from app.models.enums import DocumentStatus
from app.retrieval.parents import expand_parent_hits
from app.retrieval.tokenization import tokenize
from app.retrieval.types import RetrievalHit


def calculate_bm25_scores(
    query_terms: Sequence[str],
    postings_by_term: Mapping[str, Mapping[UUID, int]],
    document_lengths: Mapping[UUID, int],
    *,
    total_documents: int,
    average_document_length: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> dict[UUID, float]:
    """计算标准 BM25 分数。

    公式来源：Robertson & Zaragoza, "The Probabilistic Relevance Framework:
    BM25 and Beyond" (2009), 4.1 节；IDF 使用 Lucene 常用的平滑形式
    log(1 + (N - df + 0.5) / (df + 0.5))。
    """
    if total_documents <= 0 or average_document_length <= 0:
        return {}

    scores: dict[UUID, float] = defaultdict(float)
    unique_terms = list(dict.fromkeys(query_terms))
    for term in unique_terms:
        postings = postings_by_term.get(term, {})
        document_frequency = len(postings)
        if document_frequency == 0:
            continue
        inverse_document_frequency = math.log(
            1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
        )
        for chunk_id, term_frequency in postings.items():
            document_length = document_lengths.get(chunk_id, 0)
            normalization = 1 - b + b * document_length / average_document_length
            denominator = term_frequency + k1 * normalization
            scores[chunk_id] += inverse_document_frequency * (
                term_frequency * (k1 + 1) / denominator
            )
    return dict(scores)


async def bm25_search(
    session: AsyncSession,
    query: str,
    *,
    top_k: int,
) -> list[RetrievalHit]:
    """从 chunk_terms 读取 posting，按标准 BM25 公式排序返回切片。"""
    query_terms = list(dict.fromkeys(tokenize(query)))
    if not query_terms:
        return []

    total_documents = await session.scalar(
        select(func.count(func.distinct(ChunkTerm.chunk_id)))
        .join(Chunk, Chunk.id == ChunkTerm.chunk_id)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Document.status == DocumentStatus.READY,
            Chunk.is_parent.is_(False),
        )
    )
    if not total_documents:
        return []

    length_subquery = (
        select(
            ChunkTerm.chunk_id.label("chunk_id"),
            func.sum(ChunkTerm.term_frequency).label("document_length"),
        )
        .join(Chunk, Chunk.id == ChunkTerm.chunk_id)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Document.status == DocumentStatus.READY,
            Chunk.is_parent.is_(False),
        )
        .group_by(ChunkTerm.chunk_id)
        .subquery()
    )
    average_length = await session.scalar(select(func.avg(length_subquery.c.document_length)))
    average_document_length = float(average_length or 0)
    if average_document_length <= 0:
        return []

    posting_rows = (
        await session.execute(
            select(
                ChunkTerm.term,
                ChunkTerm.chunk_id,
                ChunkTerm.term_frequency,
            ).where(ChunkTerm.term.in_(query_terms))
        )
    ).all()
    postings_by_term: dict[str, dict[UUID, int]] = defaultdict(dict)
    for term, chunk_id, term_frequency in posting_rows:
        postings_by_term[cast(str, term)][cast(UUID, chunk_id)] = cast(int, term_frequency)

    candidate_ids = {chunk_id for postings in postings_by_term.values() for chunk_id in postings}
    if not candidate_ids:
        return []

    document_lengths = {
        cast(UUID, chunk_id): cast(int, document_length)
        for chunk_id, document_length in (
            await session.execute(
                select(
                    ChunkTerm.chunk_id,
                    func.sum(ChunkTerm.term_frequency).label("document_length"),
                )
                .where(ChunkTerm.chunk_id.in_(candidate_ids))
                .group_by(ChunkTerm.chunk_id)
            )
        ).all()
    }
    scores = calculate_bm25_scores(
        query_terms,
        postings_by_term,
        document_lengths,
        total_documents=int(total_documents),
        average_document_length=average_document_length,
    )
    ranked_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], str(chunk_id)))[:top_k]

    metadata_rows = (
        (
            await session.execute(
                select(
                    Chunk.id,
                    Chunk.document_id,
                    Chunk.content,
                    Chunk.page_number,
                    Chunk.heading_path,
                    Document.filename,
                )
                .join(Document, Document.id == Chunk.document_id)
                .where(
                    Chunk.id.in_(ranked_ids),
                    Chunk.is_parent.is_(False),
                )
            )
        )
        .mappings()
        .all()
    )
    metadata = {cast(UUID, row["id"]): row for row in metadata_rows}

    results: list[RetrievalHit] = []
    for chunk_id in ranked_ids:
        row = metadata.get(chunk_id)
        if row is None:
            continue
        results.append(
            RetrievalHit(
                chunk_id=chunk_id,
                document_id=cast(UUID, row["document_id"]),
                content=cast(str, row["content"]),
                document_name=cast(str, row["filename"]),
                page_number=cast(int | None, row["page_number"]),
                heading_path=tuple(cast(list[str], row["heading_path"])),
                score=scores[chunk_id],
                sources=("bm25",),
            )
        )
    return await expand_parent_hits(session, results)
