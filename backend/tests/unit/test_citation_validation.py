from collections.abc import AsyncIterator, Sequence
from uuid import uuid4

import pytest
from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    LLMMessage,
    LLMProvider,
    LLMStreamEvent,
    TokenUsage,
)
from app.rag.citation_validation import (
    CitationSemanticValidator,
    CitationValidationError,
)
from app.rag.types import RAGContext
from app.retrieval.types import RetrievalHit


class StubProvider(LLMProvider):
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
        return ChatResult(text=response, usage=TokenUsage(), finish_reason="stop")

    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: str | None = None,
    ) -> EmbeddingResult:
        raise NotImplementedError


def _context() -> RAGContext:
    return RAGContext(
        citation_number=1,
        hit=RetrievalHit(
            chunk_id=uuid4(),
            document_id=uuid4(),
            content="住宿标准为每晚 500 元。",
            document_name="policy.md",
            page_number=1,
            heading_path=(),
            score=1.0,
            sources=("vector",),
        ),
    )


@pytest.mark.asyncio
async def test_validator_retries_invalid_json_then_accepts_supported_answer() -> None:
    provider = StubProvider(
        [
            '{"sentences":"invalid"}',
            '{"sentences":[{"sentence":"住宿标准为 500 元。[1]","citations":[1],'
            '"supported":true,"reason":"片段明确支持"}]}',
        ]
    )

    result = await CitationSemanticValidator(provider=provider).validate(
        question="住宿标准是多少？",
        answer="住宿标准为 500 元。[1]",
        contexts=[_context()],
    )

    assert result.valid is True
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_validator_marks_unsupported_sentence() -> None:
    provider = StubProvider(
        [
            '{"sentences":[{"sentence":"提供免费晚餐。[1]","citations":[1],'
            '"supported":false,"reason":"证据没有提到晚餐"}]}'
        ]
    )

    result = await CitationSemanticValidator(provider=provider).validate(
        question="福利是什么？",
        answer="提供免费晚餐。[1]",
        contexts=[_context()],
    )

    assert result.valid is False
    assert result.unsupported_sentences == ("提供免费晚餐。[1]",)


@pytest.mark.asyncio
async def test_validator_rejects_out_of_range_citations_after_retry() -> None:
    response = (
        '{"sentences":[{"sentence":"无依据。[2]","citations":[2],'
        '"supported":true,"reason":"错误引用"}]}'
    )

    with pytest.raises(CitationValidationError):
        await CitationSemanticValidator(provider=StubProvider([response, response])).validate(
            question="问题",
            answer="无依据。[2]",
            contexts=[_context()],
        )
