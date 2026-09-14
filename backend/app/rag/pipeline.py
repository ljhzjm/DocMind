from collections.abc import AsyncIterator
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.llm.base import LLMError
from app.rag.answer import AnswerGenerator, RAGGenerationError
from app.rag.query_rewrite import QueryRewriter
from app.rag.rerank import RerankConfigurationError, RerankProvider, create_reranker
from app.rag.types import (
    AnswerDeltaEvent,
    DoneEvent,
    ErrorEvent,
    RAGContext,
    RAGStreamEvent,
    RetrievalEvent,
)
from app.retrieval.embedding import EmbeddingError
from app.retrieval.service import SearchService
from app.retrieval.types import SearchMode

_REFUSAL_ANSWER = "未找到相关资料"


class RAGPipeline:
    """查询改写 -> 混合检索 -> 重排/拒答 -> 结构化生成 -> SSE 事件。"""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        search_service: SearchService | None = None,
        query_rewriter: QueryRewriter | None = None,
        reranker: RerankProvider | None = None,
        answer_generator: AnswerGenerator | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._search_service = search_service or SearchService()
        self._query_rewriter = query_rewriter or QueryRewriter()
        self._reranker = reranker or create_reranker(self._settings)
        self._answer_generator = answer_generator or AnswerGenerator()

    async def stream(
        self,
        session: AsyncSession,
        query: str,
        *,
        top_k: int | None = None,
    ) -> AsyncIterator[RAGStreamEvent]:
        started_at = perf_counter()
        try:
            rewrite = await self._query_rewriter.rewrite(query)
            search_mode = self._parse_mode(self._settings.rag_retrieval_mode)
            candidates = await self._search_service.search(
                session,
                query=rewrite.retrieval_query,
                mode=search_mode,
                top_k=self._settings.rag_candidate_top_k,
            )
            reranked = await self._reranker.rerank(
                query,
                candidates,
                top_k=top_k or self._settings.rag_context_top_k,
            )
            retrieval_latency_ms = round((perf_counter() - started_at) * 1000, 3)
            yield RetrievalEvent(
                latency_ms=retrieval_latency_ms,
                chunk_count=len(reranked),
            )

            if not reranked or reranked[0].score < self._settings.rag_refusal_threshold:
                async for event in self._refusal_events():
                    yield event
                return

            contexts = [
                RAGContext(citation_number=index, hit=hit)
                for index, hit in enumerate(reranked, start=1)
            ]
            answer = await self._answer_generator.generate(query, contexts)
            for delta in self._split_text(answer.answer):
                yield AnswerDeltaEvent(delta=delta)
            yield DoneEvent(citations=answer.citations)
        except (
            LLMError,
            EmbeddingError,
            RerankConfigurationError,
            RAGGenerationError,
            ValueError,
        ) as exc:
            yield ErrorEvent(message=str(exc))

    async def _refusal_events(self) -> AsyncIterator[RAGStreamEvent]:
        """低相关度时直接拒答，不调用生成模型。"""
        for delta in self._split_text(_REFUSAL_ANSWER):
            yield AnswerDeltaEvent(delta=delta)
        yield DoneEvent(citations=[])

    @staticmethod
    def _parse_mode(value: str) -> SearchMode:
        try:
            return SearchMode(value)
        except ValueError:
            return SearchMode.HYBRID

    @staticmethod
    def _split_text(text: str, chunk_size: int = 24) -> list[str]:
        return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]
