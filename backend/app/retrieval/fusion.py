from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from app.retrieval.types import RetrievalHit

RRF_K = 60


def rrf_fuse(
    vector_results: Sequence[RetrievalHit],
    bm25_results: Sequence[RetrievalHit],
    *,
    top_k: int,
    k: int = RRF_K,
) -> list[RetrievalHit]:
    """按 Reciprocal Rank Fusion 融合两路排名：score += 1 / (k + rank)。"""
    scores: dict[UUID, float] = defaultdict(float)
    hits: dict[UUID, RetrievalHit] = {}
    sources: dict[UUID, set[str]] = defaultdict(set)

    for results in (vector_results, bm25_results):
        for rank, hit in enumerate(results, start=1):
            key = hit.chunk_id
            hits.setdefault(key, hit)
            sources[key].update(hit.sources)
            scores[key] += 1 / (k + rank)

    fused = [
        RetrievalHit(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            content=hit.content,
            document_name=hit.document_name,
            page_number=hit.page_number,
            heading_path=hit.heading_path,
            score=scores[chunk_id],
            sources=tuple(sorted(sources[chunk_id])),
        )
        for chunk_id, hit in hits.items()
    ]
    fused.sort(key=lambda item: (-item.score, str(item.chunk_id)))
    return fused[:top_k]
