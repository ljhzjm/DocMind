from uuid import UUID, uuid4

from app.retrieval.bm25 import calculate_bm25_scores
from app.retrieval.fusion import rrf_fuse
from app.retrieval.types import RetrievalHit


def hit(chunk_id: UUID, name: str, score: float, *sources: str) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        document_id=uuid4(),
        content=name,
        document_name=f"{name}.md",
        page_number=1,
        heading_path=("Guide",),
        score=score,
        sources=tuple(sources),
    )


def test_bm25_recovers_exact_term_that_vector_search_missed() -> None:
    semantic_document = uuid4()
    exact_term_document = uuid4()
    common_document = uuid4()
    postings = {"transformer": {exact_term_document: 2}}

    scores = calculate_bm25_scores(
        ["transformer"],
        postings,
        {
            semantic_document: 10,
            exact_term_document: 10,
            common_document: 10,
        },
        total_documents=3,
        average_document_length=10,
    )

    vector_results = [
        hit(semantic_document, "semantic", 0.91, "vector"),
        hit(common_document, "common", 0.84, "vector"),
    ]
    bm25_results = [
        hit(
            exact_term_document, "exact transformer reference", scores[exact_term_document], "bm25"
        ),
        hit(common_document, "common", 1.0, "bm25"),
    ]
    fused = rrf_fuse(vector_results, bm25_results, top_k=10)

    assert exact_term_document not in {result.chunk_id for result in vector_results}
    assert max(scores, key=scores.__getitem__) == exact_term_document
    assert exact_term_document in {result.chunk_id for result in fused}
    assert any(result.sources == ("bm25", "vector") for result in fused)


def test_rrf_scores_shared_hit_with_both_rank_contributions() -> None:
    shared = uuid4()
    vector_only = uuid4()
    bm25_only = uuid4()
    vector_results = [
        hit(shared, "shared", 0.9, "vector"),
        hit(vector_only, "vector", 0.8, "vector"),
    ]
    bm25_results = [
        hit(bm25_only, "bm25", 5.0, "bm25"),
        hit(shared, "shared", 4.0, "bm25"),
    ]

    fused = rrf_fuse(vector_results, bm25_results, top_k=3)

    shared_result = next(result for result in fused if result.chunk_id == shared)
    assert shared_result.sources == ("bm25", "vector")
    assert shared_result.score == (1 / 61) + (1 / 62)
