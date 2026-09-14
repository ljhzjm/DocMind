from collections.abc import AsyncIterator, Sequence
from typing import cast
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    LLMMessage,
    LLMProvider,
    LLMStreamEvent,
    TokenUsage,
)
from app.rag.answer import (
    AnswerGenerator,
    CitationValidationError,
    RAGGenerationError,
    validate_answer,
)
from app.rag.pipeline import RAGPipeline
from app.rag.query_rewrite import QueryRewriter, RewriteResult
from app.rag.rerank import PassthroughReranker
from app.rag.types import AnswerDeltaEvent, DoneEvent, RAGAnswer, RAGContext, RetrievalEvent
from app.retrieval.service import SearchService
from app.retrieval.types import RetrievalHit, SearchMode
from pydantic import ValidationError
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
    generator = AnswerGenerator(provider=provider)

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
    )

    events = [event async for event in pipeline.stream(cast(AsyncSession, object()), "question")]
    answer = "".join(event.delta for event in events if isinstance(event, AnswerDeltaEvent))

    assert isinstance(events[0], RetrievalEvent)
    assert answer == "未找到相关资料"
    assert isinstance(events[-1], DoneEvent)
    assert generator.calls == 0
