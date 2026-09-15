from collections.abc import AsyncIterator, Sequence
from typing import cast
from uuid import uuid4

import pytest
from app.evaluation.judge import JudgeResult, JudgeService
from app.evaluation.ragas_adapter import RagasEvaluator, RagasScores
from app.evaluation.runner import EvaluationRunner
from app.evaluation.types import EvalCase, EvaluationProgress, RetrievalConfig
from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    LLMMessage,
    LLMProvider,
    LLMStreamEvent,
    TokenUsage,
)
from app.rag.answer import AnswerGenerator
from app.rag.rerank import PassthroughReranker
from app.rag.types import GenerationOutcome, RAGContext
from app.retrieval.service import SearchService
from app.retrieval.types import RetrievalHit, SearchMode
from sqlalchemy.ext.asyncio import AsyncSession


class EmptySearchService(SearchService):
    async def search(
        self,
        session: AsyncSession,
        *,
        query: str,
        mode: SearchMode,
        top_k: int,
    ) -> list[RetrievalHit]:
        del session, query, mode, top_k
        return []


class FailIfCalledGenerator(AnswerGenerator):
    async def generate_with_metadata(
        self,
        query: str,
        contexts: Sequence[RAGContext],
        *,
        max_retries: int = 1,
    ) -> GenerationOutcome:
        del query, contexts, max_retries
        raise AssertionError("generation must not run for empty retrieval")


class FailIfCalledJudge(JudgeService):
    async def score(
        self,
        *,
        question: str,
        reference_answer: str,
        answer: str,
        contexts: Sequence[str],
    ) -> JudgeResult:
        del question, reference_answer, answer, contexts
        raise AssertionError("judge must not run for empty retrieval")


class StaticRagas(RagasEvaluator):
    def __init__(self) -> None:
        pass

    async def score(
        self,
        *,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> RagasScores:
        del question, answer, contexts
        return RagasScores(faithfulness=1.0, answer_relevance=1.0)


@pytest.mark.asyncio
async def test_runner_handles_empty_retrieval_without_generation() -> None:
    case = EvalCase(
        id=uuid4(),
        question="unknown question",
        reference_answer="unknown reference",
        expected_chunk_ids=(uuid4(),),
        tags=(),
    )
    runner = EvaluationRunner(
        search_service=EmptySearchService(),
        reranker=PassthroughReranker(),
        answer_generator=FailIfCalledGenerator(),
        judge=FailIfCalledJudge(),
        ragas_evaluator=StaticRagas(),
    )
    progress: list[tuple[int, int, int, int]] = []

    async def report(event: EvaluationProgress) -> None:
        progress.append(
            (
                event.completed,
                event.total,
                event.config_index,
                event.case_index,
            )
        )

    results = await runner.run(
        cast(AsyncSession, object()),
        cases=[case],
        configs=[
            RetrievalConfig(
                name="bm25",
                mode=SearchMode.BM25,
                top_k=5,
                rerank=False,
            )
        ],
        progress_callback=report,
    )

    assert results[0].recall_at_5 == 0
    assert results[0].mrr == 0
    assert results[0].cases[0].error == "empty retrieval result"
    assert progress == [(1, 1, 0, 0)]


class JudgeStubProvider(LLMProvider):
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
            usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            finish_reason="stop",
        )

    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: str | None = None,
    ) -> EmbeddingResult:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_judge_retries_after_invalid_structured_output() -> None:
    provider = JudgeStubProvider(
        [
            '{"faithfulness":"high","answer_relevance":5}',
            '{"faithfulness":4,"answer_relevance":5,'
            '"faithfulness_reason":"supported",'
            '"relevance_reason":"direct"}',
        ]
    )

    result = await JudgeService(provider=provider).score(
        question="question",
        reference_answer="reference",
        answer="answer",
        contexts=["context"],
    )

    assert provider.calls == 2
    assert result.faithfulness == 4
    assert result.answer_relevance == 5
