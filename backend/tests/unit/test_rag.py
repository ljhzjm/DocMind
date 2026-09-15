from collections.abc import AsyncIterator, Sequence
from typing import cast
from uuid import uuid4

import pytest
from app.cache.answer_cache import AnswerCache, CachedAnswer
from app.core.config import Settings
from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    FinishEvent,
    LLMMessage,
    LLMProvider,
    LLMStreamEvent,
    TextDeltaEvent,
    TokenUsage,
)
from app.models.enums import UsageStep
from app.observability.trace import TraceRecorder
from app.rag.answer import (
    AnswerGenerator,
    RAGGenerationError,
    validate_answer,
)
from app.rag.citation_validation import (
    CitationSemanticValidator,
    CitationValidationResult,
)
from app.rag.pipeline import RAGPipeline
from app.rag.query_rewrite import QueryRewriter, RewriteResult
from app.rag.rerank import PassthroughReranker
from app.rag.types import (
    AnswerDeltaEvent,
    CitationValidationError,
    DoneEvent,
    RAGAnswer,
    RAGContext,
    RetrievalEvent,
)
from app.retrieval.service import SearchService
from app.retrieval.types import RetrievalHit, SearchMode
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession


class StubLLMProvider(LLMProvider):
    def __init__(self, responses: Sequence[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def chat_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        raise NotImplementedError

    async def chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        del messages, task, temperature, max_tokens
        response = self.responses[self.calls]
        self.calls += 1
        return ChatResult(
            text=response,
            usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
            finish_reason="stop",
        )

    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: str | None = None,
    ) -> EmbeddingResult:
        raise NotImplementedError


class StubCitationValidator(CitationSemanticValidator):
    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid

    async def validate(
        self,
        *,
        question: str,
        answer: str,
        contexts: Sequence[RAGContext],
    ) -> CitationValidationResult:
        del question, contexts
        return CitationValidationResult(
            valid=self.valid,
            unsupported_sentences=() if self.valid else (answer,),
            usage=TokenUsage(),
            model_name="stub-validator",
            estimated_cost=0.0,
        )


class SequencedCitationValidator(CitationSemanticValidator):
    def __init__(self, results: Sequence[bool]) -> None:
        self.results = list(results)
        self.calls = 0

    async def validate(
        self,
        *,
        question: str,
        answer: str,
        contexts: Sequence[RAGContext],
    ) -> CitationValidationResult:
        del question, contexts
        valid = self.results[self.calls]
        self.calls += 1
        return CitationValidationResult(
            valid=valid,
            unsupported_sentences=() if valid else (answer,),
            usage=TokenUsage(),
            model_name="stub-validator",
            estimated_cost=0.0,
        )


class NoopTraceRecorder(TraceRecorder):
    async def record(
        self,
        session: AsyncSession,
        *,
        trace_id: str,
        step: UsageStep,
        model: str,
        latency_ms: float,
        usage: TokenUsage | None = None,
    ) -> None:
        del session, trace_id, step, model, latency_ms, usage

    async def store_snapshot(
        self,
        trace_id: str,
        payload: dict[str, object],
        *,
        redis: Redis | None = None,
    ) -> None:
        del trace_id, payload, redis


class EmptyAnswerCache(AnswerCache):
    def __init__(self) -> None:
        pass

    async def get(self, key: str) -> CachedAnswer | None:
        del key
        return None

    async def set(self, key: str, answer: CachedAnswer) -> None:
        del key, answer


async def fake_version_provider(session: object) -> str:
    del session
    return "test-version"


async def fixed_threshold_provider(
    session: object,
    mode: str,
    top_k: int,
    rerank_enabled: bool,
) -> float:
    del session, mode, top_k, rerank_enabled
    return 0.5


def context() -> RAGContext:
    return RAGContext(
        citation_number=1,
        hit=RetrievalHit(
            chunk_id=uuid4(),
            document_id=uuid4(),
            content="DocMind supports cited answers.",
            document_name="guide.md",
            page_number=1,
            heading_path=("Guide",),
            score=0.9,
            sources=("vector",),
        ),
    )


def test_validate_answer_accepts_legal_citation() -> None:
    answer = validate_answer(
        '{"answer":"DocMind supports cited answers [1].","citations":[1]}',
        max_citation=2,
    )

    assert answer.citations == [1]


def test_validate_answer_rejects_out_of_range_citation() -> None:
    with pytest.raises(CitationValidationError, match="out of range"):
        validate_answer(
            '{"answer":"Unsupported claim [3].","citations":[3]}',
            max_citation=2,
        )

    with pytest.raises(ValidationError):
        validate_answer('{"answer":""}', max_citation=2)


@pytest.mark.asyncio
async def test_answer_generator_retries_once_after_invalid_citation() -> None:
    provider = StubLLMProvider(
        [
            '{"answer":"Invalid [2]","citations":[2]}',
            '{"answer":"Valid [1]","citations":[1]}',
        ]
    )
    generator = AnswerGenerator(
        provider=provider,
        citation_validator=StubCitationValidator(),
    )

    answer = await generator.generate("question", [context()])

    assert provider.calls == 2
    assert answer.answer == "Valid [1]"
    assert answer.citations == [1]


@pytest.mark.asyncio
async def test_answer_generator_fails_after_retry_budget() -> None:
    provider = StubLLMProvider(
        [
            '{"answer":"Invalid [2]","citations":[2]}',
            '{"answer":"Still invalid [2]","citations":[2]}',
        ]
    )

    with pytest.raises(RAGGenerationError):
        await AnswerGenerator(provider=provider).generate("question", [context()])


@pytest.mark.asyncio
async def test_answer_generator_retries_semantically_unsupported_citations() -> None:
    provider = StubLLMProvider(
        [
            '{"answer":"Unsupported [1]","citations":[1]}',
            '{"answer":"Supported [1]","citations":[1]}',
        ]
    )
    validator = SequencedCitationValidator([False, True])

    answer = await AnswerGenerator(
        provider=provider,
        citation_validator=validator,
    ).generate("question", [context()])

    assert provider.calls == 2
    assert validator.calls == 2
    assert answer.answer == "Supported [1]"


class FixedSearchService(SearchService):
    def __init__(self, hits: list[RetrievalHit]) -> None:
        super().__init__()
        self.hits = hits

    async def search(
        self,
        session: AsyncSession,
        *,
        query: str,
        mode: SearchMode,
        top_k: int,
    ) -> list[RetrievalHit]:
        del session, query, mode, top_k
        return self.hits


class FixedQueryRewriter(QueryRewriter):
    async def rewrite(self, query: str) -> RewriteResult:
        return RewriteResult(query=query, keywords=[])


class CountingAnswerGenerator(AnswerGenerator):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def generate(
        self,
        query: str,
        contexts: Sequence[RAGContext],
        *,
        max_retries: int = 1,
    ) -> RAGAnswer:
        del max_retries
        self.calls += 1
        raise AssertionError("generator must not run for low-score refusal")


@pytest.mark.asyncio
async def test_pipeline_refuses_low_score_without_generation() -> None:
    low_score_hit = RetrievalHit(
        chunk_id=uuid4(),
        document_id=uuid4(),
        content="weak result",
        document_name="weak.md",
        page_number=None,
        heading_path=(),
        score=0.1,
        sources=("bm25",),
    )
    generator = CountingAnswerGenerator()
    pipeline = RAGPipeline(
        settings=Settings(rag_refusal_threshold=0.5),
        search_service=FixedSearchService([low_score_hit]),
        query_rewriter=FixedQueryRewriter(),
        reranker=PassthroughReranker(),
        answer_generator=generator,
        answer_cache=EmptyAnswerCache(),
        trace_recorder=NoopTraceRecorder(),
        knowledge_base_version_provider=fake_version_provider,
        refusal_threshold_provider=fixed_threshold_provider,
    )

    events = [event async for event in pipeline.stream(cast(AsyncSession, object()), "question")]
    answer = "".join(event.delta for event in events if isinstance(event, AnswerDeltaEvent))
    done_event = next(event for event in events if isinstance(event, DoneEvent))

    assert isinstance(events[0], RetrievalEvent)
    assert answer == "未找到相关资料"
    assert done_event.citations == []
    assert generator.calls == 0


class StreamingStubProvider(StubLLMProvider):
    def __init__(self, streams: Sequence[Sequence[str]]) -> None:
        super().__init__([])
        self.streams = [list(stream) for stream in streams]

    def chat_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        del messages, task, temperature, max_tokens
        stream = self.streams[self.calls]
        self.calls += 1

        async def events() -> AsyncIterator[LLMStreamEvent]:
            for chunk in stream:
                yield TextDeltaEvent(text=chunk)
            yield FinishEvent(finish_reason="stop")

        return events()


@pytest.mark.asyncio
async def test_answer_generator_streams_only_after_valid_citations() -> None:
    provider = StreamingStubProvider(
        [
            ['{"citations":[2],', '"answer":"invalid [2]"}'],
            ['{"citations":[1],"answer":"合', '法 [1]"}'],
        ]
    )

    events = [
        event
        async for event in AnswerGenerator(
            provider=provider,
            citation_validator=StubCitationValidator(),
        ).stream("question", [context()])
    ]
    deltas = [event.delta for event in events if isinstance(event, AnswerDeltaEvent)]

    done_event = next(event for event in events if isinstance(event, DoneEvent))
    assert provider.calls == 2
    assert "".join(deltas) == "合法 [1]"
    assert done_event.citations == [1]
