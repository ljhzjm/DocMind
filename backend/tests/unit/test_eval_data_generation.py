from collections.abc import AsyncIterator, Sequence
from uuid import uuid4

import pytest
from app.evaluation.dataset_generation import (
    NEGATIVE_REFERENCE_ANSWER,
    EvalDataGenerator,
    EvidenceChunk,
    GeneratedEvalCase,
    normalize_import_records,
    question_type_counts,
)
from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    LLMMessage,
    LLMProvider,
    LLMStreamEvent,
    TokenUsage,
)


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


def _evidence() -> list[EvidenceChunk]:
    first_document = uuid4()
    second_document = uuid4()
    return [
        EvidenceChunk(
            chunk_id=uuid4(),
            document_id=first_document,
            document_name="policy.md",
            page_number=1,
            heading_path=("报销", "标准"),
            content="员工差旅住宿标准为每晚 500 元。",
        ),
        EvidenceChunk(
            chunk_id=uuid4(),
            document_id=second_document,
            document_name="history.md",
            page_number=2,
            heading_path=("调整记录",),
            content="2025 年住宿标准由 400 元调整为 500 元。",
        ),
    ]


@pytest.mark.asyncio
async def test_generator_maps_evidence_indexes_to_leaf_chunk_ids() -> None:
    evidence = _evidence()
    provider = StubProvider(
        [
            '{"question":"住宿标准是多少？","reference_answer":"每晚 500 元。",'
            '"evidence_indexes":[1]}'
        ]
    )

    record = await EvalDataGenerator(provider=provider).generate(
        dataset_name="test",
        question_type="factual",
        evidence=evidence,
        existing_questions=[],
        created_by="tester",
    )

    assert record.expected_chunk_ids == [evidence[0].chunk_id]
    assert record.review_status == "pending"


@pytest.mark.asyncio
async def test_generator_forces_canonical_negative_answer() -> None:
    provider = StubProvider(
        [
            '{"question":"公司有几个海外办公室？","reference_answer":"无法回答",'
            '"evidence_indexes":[]}'
        ]
    )

    record = await EvalDataGenerator(provider=provider).generate(
        dataset_name="test",
        question_type="out_of_kb",
        evidence=_evidence(),
        existing_questions=[],
        created_by="tester",
    )

    assert record.reference_answer == NEGATIVE_REFERENCE_ANSWER
    assert record.expected_chunk_ids == []
    assert "negative" in record.tags


@pytest.mark.asyncio
async def test_generator_retries_invalid_evidence_index() -> None:
    evidence = _evidence()
    provider = StubProvider(
        [
            '{"question":"对比标准变化","reference_answer":"标准提高","evidence_indexes":[9]}',
            '{"question":"两份文档中的住宿标准有何变化？",'
            '"reference_answer":"先从 400 元调整为 500 元。","evidence_indexes":[1,2]}',
        ]
    )

    record = await EvalDataGenerator(provider=provider).generate(
        dataset_name="test",
        question_type="multi_document",
        evidence=evidence,
        existing_questions=[],
        created_by="tester",
    )

    assert provider.calls == 2
    assert record.expected_chunk_ids == [evidence[0].chunk_id, evidence[1].chunk_id]


def test_import_validation_rejects_negative_with_expected_chunks() -> None:
    record = GeneratedEvalCase(
        dataset_name="test",
        question_type="out_of_kb",
        question="知识库外问题",
        reference_answer=NEGATIVE_REFERENCE_ANSWER,
        expected_chunk_ids=[uuid4()],
        review_status="approved",
        created_by="reviewer",
    )

    with pytest.raises(ValueError, match="invalid negative sample"):
        normalize_import_records([record])


def test_import_validation_rejects_positive_with_negative_reference() -> None:
    record = GeneratedEvalCase(
        dataset_name="test",
        question_type="factual",
        question="正样本问题",
        reference_answer=NEGATIVE_REFERENCE_ANSWER,
        expected_chunk_ids=[uuid4()],
        review_status="approved",
        created_by="reviewer",
    )

    with pytest.raises(ValueError, match="positive sample has negative reference"):
        normalize_import_records([record])


def test_question_type_counts_keep_negative_samples_near_twenty_percent() -> None:
    counts = question_type_counts(40)

    assert sum(counts.values()) == 40
    assert counts["out_of_kb"] == 8
    assert counts["multi_document"] > 0
