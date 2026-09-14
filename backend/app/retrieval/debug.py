from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.llm.base import LLMError
from app.rag.query_rewrite import QueryRewriter
from app.rag.rerank import RerankProvider, create_reranker
from app.retrieval.bm25 import bm25_search
from app.retrieval.embedding import EmbeddingError, EmbeddingProvider, LLMGatewayEmbeddingProvider
from app.retrieval.fusion import rrf_fuse
from app.retrieval.types import RetrievalHit
from app.retrieval.vector import vector_search


@dataclass(frozen=True)
class SearchStepTrace:
    latency_ms: float
    results: list[RetrievalHit]
    error: str | None = None


@dataclass(frozen=True)
class SearchDebugTrace:
    query: str
    rewritten_query: str
    keywords: list[str]
    rewrite_latency_ms: float
    vector: SearchStepTrace
    bm25: SearchStepTrace
    fusion: SearchStepTrace
    rerank: SearchStepTrace


class SearchDebugService:
    """执行并分别记录改写、向量、BM25、RRF 和重排步骤。"""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        query_rewriter: QueryRewriter | None = None,
        reranker: RerankProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._embedding_provider = embedding_provider or LLMGatewayEmbeddingProvider()
        self._query_rewriter = query_rewriter or QueryRewriter()
        self._reranker = reranker or create_reranker(self._settings)

    async def run(
        self,
        session: AsyncSession,
        query: str,
        *,
        top_k: int,
    ) -> SearchDebugTrace:
        rewrite_started = perf_counter()
        rewrite = await self._query_rewriter.rewrite(query)
        rewrite_latency = self._elapsed_ms(rewrite_started)

        candidate_k = max(top_k * 3, top_k)
        vector = await self._vector_step(
            session,
            rewrite.retrieval_query,
            candidate_k,
        )
        bm25 = await self._bm25_step(session, rewrite.retrieval_query, candidate_k)

        fusion_started = perf_counter()
        fused = rrf_fuse(vector.results, bm25.results, top_k=candidate_k)
        fusion = SearchStepTrace(
            latency_ms=self._elapsed_ms(fusion_started),
            results=fused,
        )

        rerank_started = perf_counter()
        reranked = await self._reranker.rerank(query, fused, top_k=top_k)
        rerank = SearchStepTrace(
            latency_ms=self._elapsed_ms(rerank_started),
            results=reranked,
        )

        return SearchDebugTrace(
            query=query,
            rewritten_query=rewrite.query,
            keywords=rewrite.keywords,
            rewrite_latency_ms=rewrite_latency,
            vector=vector,
            bm25=bm25,
            fusion=fusion,
            rerank=rerank,
        )

    async def _vector_step(
        self,
        session: AsyncSession,
        query: str,
        top_k: int,
    ) -> SearchStepTrace:
        started = perf_counter()
        try:
            results = await vector_search(
                session,
                self._embedding_provider,
                query,
                top_k=top_k,
            )
            return SearchStepTrace(self._elapsed_ms(started), results)
        except (LLMError, EmbeddingError) as exc:
            return SearchStepTrace(
                latency_ms=self._elapsed_ms(started),
                results=[],
                error=str(exc),
            )

    async def _bm25_step(
        self,
        session: AsyncSession,
        query: str,
        top_k: int,
    ) -> SearchStepTrace:
        started = perf_counter()
        results = await bm25_search(session, query, top_k=top_k)
        return SearchStepTrace(self._elapsed_ms(started), results)

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 3)
