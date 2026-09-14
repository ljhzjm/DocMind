import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.answer_cache import (
    AnswerCache,
    CachedAnswer,
    CachedContext,
    cache_key,
    knowledge_base_version,
)
from app.core.config import Settings, get_settings
from app.llm.base import LLMError
from app.models.enums import UsageStep
from app.observability.context import trace_id_context
from app.observability.trace import TraceRecorder
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
from app.retrieval.types import RetrievalHit, SearchMode

_REFUSAL_ANSWER = "未找到相关资料"
KnowledgeBaseVersionProvider = Callable[[AsyncSession], Awaitable[str]]


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
        answer_cache: AnswerCache | None = None,
        trace_recorder: TraceRecorder | None = None,
        knowledge_base_version_provider: KnowledgeBaseVersionProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._search_service = search_service or SearchService()
        self._query_rewriter = query_rewriter or QueryRewriter()
        self._reranker = reranker or create_reranker(self._settings)
        self._answer_generator = answer_generator or AnswerGenerator()
        self._answer_cache = answer_cache or AnswerCache()
        self._trace_recorder = trace_recorder or TraceRecorder()
        self._knowledge_base_version_provider = (
            knowledge_base_version_provider or knowledge_base_version
        )

    async def stream(
        self,
        session: AsyncSession,
        query: str,
        *,
        top_k: int | None = None,
        trace_id: str | None = None,
    ) -> AsyncIterator[RAGStreamEvent]:
        active_trace_id = trace_id or uuid4().hex
        context_token = trace_id_context.set(active_trace_id)
        started_at = perf_counter()
        search_mode = self._parse_mode(self._settings.rag_retrieval_mode)
        effective_top_k = top_k or self._settings.rag_context_top_k

        try:
            version = await self._knowledge_base_version_provider(session)
            key = cache_key(
                query=query,
                knowledge_base_version=version,
                retrieval_config=self._retrieval_config_signature(
                    search_mode,
                    effective_top_k,
                ),
            )
            cached = await self._answer_cache.get(key)
            if cached is not None:
                await self._trace_recorder.record(
                    session,
                    trace_id=active_trace_id,
                    step=UsageStep.RETRIEVE,
                    model="answer-cache",
                    latency_ms=0,
                )
                cached_hits = self._cached_hits(cached)
                await self._store_snapshot(
                    active_trace_id,
                    cached.query,
                    cached.rewritten_query,
                    cached_hits,
                    cached=True,
                )
                async for event in self._cached_events(cached, active_trace_id):
                    yield event
                return

            rewrite_started = perf_counter()
            rewrite = await self._query_rewriter.rewrite(query)
            rewrite_latency = self._elapsed_ms(rewrite_started)
            await self._trace_recorder.record(
                session,
                trace_id=active_trace_id,
                step=UsageStep.REWRITE,
                model=rewrite.model_name,
                latency_ms=rewrite_latency,
                usage=rewrite.usage,
            )

            retrieval_started = perf_counter()
            candidates = await self._search_service.search(
                session,
                query=rewrite.retrieval_query,
                mode=search_mode,
                top_k=self._settings.rag_candidate_top_k,
            )
            await self._trace_recorder.record(
                session,
                trace_id=active_trace_id,
                step=UsageStep.RETRIEVE,
                model=f"{search_mode.value}-search",
                latency_ms=self._elapsed_ms(retrieval_started),
            )

            rerank_started = perf_counter()
            reranked = await self._reranker.rerank(
                query,
                candidates,
                top_k=effective_top_k,
            )
            await self._trace_recorder.record(
                session,
                trace_id=active_trace_id,
                step=UsageStep.RERANK,
                model=self._reranker.__class__.__name__,
                latency_ms=self._elapsed_ms(rerank_started),
            )

            retrieval_latency_ms = round((perf_counter() - started_at) * 1000, 3)
            contexts = [
                RAGContext(citation_number=index, hit=hit)
                for index, hit in enumerate(reranked, start=1)
            ]
            yield RetrievalEvent(
                latency_ms=retrieval_latency_ms,
                chunk_count=len(reranked),
                contexts=tuple(contexts),
                trace_id=active_trace_id,
            )

            if not reranked or reranked[0].score < self._settings.rag_refusal_threshold:
                await self._answer_cache.set(
                    key,
                    CachedAnswer(
                        query=query,
                        rewritten_query=rewrite.query,
                        answer=_REFUSAL_ANSWER,
                        citations=[],
                        contexts=[self._cached_context(context) for context in contexts],
                        trace_id=active_trace_id,
                    ),
                )
                await self._store_snapshot(
                    active_trace_id,
                    query,
                    rewrite.query,
                    reranked,
                    cached=False,
                )
                async for event in self._refusal_events(active_trace_id):
                    yield event
                return

            generated_text = ""
            generation_started = perf_counter()
            async for event in self._answer_generator.stream(query, contexts):
                if isinstance(event, AnswerDeltaEvent):
                    generated_text += event.delta
                    yield event
                elif isinstance(event, DoneEvent):
                    await self._trace_recorder.record(
                        session,
                        trace_id=active_trace_id,
                        step=UsageStep.GENERATE,
                        model=event.model_name or "generation-model",
                        latency_ms=self._elapsed_ms(generation_started),
                        usage=event.usage,
                    )
                    await self._answer_cache.set(
                        key,
                        CachedAnswer(
                            query=query,
                            rewritten_query=rewrite.query,
                            answer=generated_text,
                            citations=event.citations,
                            contexts=[self._cached_context(context) for context in contexts],
                            trace_id=active_trace_id,
                        ),
                    )
                    await self._store_snapshot(
                        active_trace_id,
                        query,
                        rewrite.query,
                        reranked,
                        cached=False,
                    )
                    yield DoneEvent(
                        citations=event.citations,
                        trace_id=active_trace_id,
                        usage=event.usage,
                        model_name=event.model_name,
                    )
        except (
            LLMError,
            EmbeddingError,
            RerankConfigurationError,
            RAGGenerationError,
            ValueError,
        ) as exc:
            yield ErrorEvent(message=str(exc), trace_id=active_trace_id)
        finally:
            trace_id_context.reset(context_token)

    @staticmethod
    def _cached_hits(cached: CachedAnswer) -> list[RetrievalHit]:
        return [
            RetrievalHit(
                chunk_id=UUID(context.chunk_id),
                document_id=UUID(context.document_id),
                content=context.content,
                document_name=context.document_name,
                page_number=context.page_number,
                heading_path=tuple(context.heading_path),
                score=context.score,
                sources=("cache",),
            )
            for context in cached.contexts
        ]

    async def _cached_events(
        self,
        cached: CachedAnswer,
        trace_id: str,
    ) -> AsyncIterator[RAGStreamEvent]:
        contexts = tuple(
            RAGContext(
                citation_number=context.citation_number,
                hit=hit,
            )
            for context, hit in zip(
                cached.contexts,
                self._cached_hits(cached),
                strict=True,
            )
        )
        yield RetrievalEvent(
            latency_ms=0,
            chunk_count=len(contexts),
            contexts=contexts,
            trace_id=trace_id,
            cached=True,
        )
        for index in range(0, len(cached.answer), 24):
            yield AnswerDeltaEvent(delta=cached.answer[index : index + 24])
        yield DoneEvent(
            citations=cached.citations,
            trace_id=trace_id,
            model_name="answer-cache",
        )

    async def _refusal_events(self, trace_id: str) -> AsyncIterator[RAGStreamEvent]:
        for character in _REFUSAL_ANSWER:
            yield AnswerDeltaEvent(delta=character)
            await asyncio.sleep(0.03)
        yield DoneEvent(citations=[], trace_id=trace_id, model_name="refusal")

    async def _store_snapshot(
        self,
        trace_id: str,
        query: str,
        rewritten_query: str,
        hits: list[RetrievalHit],
        *,
        cached: bool,
    ) -> None:
        await self._trace_recorder.store_snapshot(
            trace_id,
            {
                "trace_id": trace_id,
                "query": query,
                "rewritten_query": rewritten_query,
                "cached": cached,
                "chunks": [
                    {
                        "chunk_id": str(hit.chunk_id),
                        "document_name": hit.document_name,
                        "page_number": hit.page_number,
                        "score": hit.score,
                        "sources": list(hit.sources),
                    }
                    for hit in hits
                ],
            },
        )

    def _retrieval_config_signature(
        self,
        mode: SearchMode,
        top_k: int,
    ) -> str:
        return ":".join(
            [
                mode.value,
                str(self._settings.rag_candidate_top_k),
                str(top_k),
                self._settings.rerank_provider,
                str(self._settings.rerank_enabled),
            ]
        )

    @staticmethod
    def _cached_context(context: RAGContext) -> CachedContext:
        return CachedContext(
            citation_number=context.citation_number,
            chunk_id=str(context.hit.chunk_id),
            document_id=str(context.hit.document_id),
            content=context.hit.content,
            document_name=context.hit.document_name,
            page_number=context.hit.page_number,
            heading_path=list(context.hit.heading_path),
            score=context.hit.score,
        )

    @staticmethod
    def _parse_mode(value: str) -> SearchMode:
        try:
            return SearchMode(value)
        except ValueError:
            return SearchMode.HYBRID

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 3)
