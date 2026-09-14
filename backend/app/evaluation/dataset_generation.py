from __future__ import annotations

from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.evaluation.prompts import render_evaluation_prompt
from app.llm import (
    LLMMessage,
    LLMProvider,
    LLMRouter,
    LLMTask,
    RoutedModel,
    create_default_router,
)
from app.rag.parsing import StructuredOutputError, parse_json_object

QuestionType = Literal["factual", "numeric", "multi_document", "out_of_kb"]
NEGATIVE_REFERENCE_ANSWER = "知识库中无相关信息"


def question_type_counts(count: int) -> dict[QuestionType, int]:
    """按约 20% 负样本和固定比例分配题型。"""
    if count < 5:
        raise ValueError("count must be at least 5")
    negative = max(1, round(count * 0.2))
    positive = count - negative
    factual = max(1, round(positive * 0.4))
    numeric = max(1, round(positive * 0.3))
    multi_document = positive - factual - numeric
    if multi_document < 1:
        factual -= 1
        multi_document += 1
    return {
        "factual": factual,
        "numeric": numeric,
        "multi_document": multi_document,
        "out_of_kb": negative,
    }


class EvidenceChunk(BaseModel):
    """生成阶段的证据切片，chunk_id 对应检索实际返回的叶子块。"""

    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    document_id: UUID
    document_name: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    heading_path: tuple[str, ...] = ()
    content: str = Field(min_length=1)


class GeneratedEvalCase(BaseModel):
    """可直接写入 JSONL 并供人工校对的评测样本。"""

    dataset_name: str = Field(min_length=1, max_length=255)
    question_type: QuestionType
    question: str = Field(min_length=1)
    reference_answer: str = Field(min_length=1)
    evidence_chunks: list[EvidenceChunk] = Field(default_factory=list)
    expected_chunk_ids: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    review_status: Literal["pending", "approved", "rejected"] = "pending"
    created_by: str = Field(min_length=1, max_length=255)


class _GeneratedPayload(BaseModel):
    question: str = Field(min_length=1)
    reference_answer: str = Field(min_length=1)
    evidence_indexes: list[int] = Field(default_factory=list)


class EvalDataGenerationError(RuntimeError):
    """模型没有在允许次数内返回可校验的评测样本。"""


def normalize_import_records(
    records: Sequence[GeneratedEvalCase],
    *,
    dataset_override: str | None = None,
    created_by_override: str | None = None,
) -> list[GeneratedEvalCase]:
    """校验人工校对结果，并统一导入所需的 dataset_name 和 tags。"""
    normalized: list[GeneratedEvalCase] = []
    for record in records:
        dataset_name = dataset_override or record.dataset_name
        created_by = created_by_override or record.created_by
        if record.question_type == "out_of_kb":
            if record.expected_chunk_ids or record.reference_answer != NEGATIVE_REFERENCE_ANSWER:
                raise ValueError(f"invalid negative sample: {record.question}")
            update = {
                "dataset_name": dataset_name,
                "created_by": created_by,
                "tags": list(dict.fromkeys([*record.tags, record.question_type, "negative"])),
                "evidence_chunks": [],
                "expected_chunk_ids": [],
            }
        else:
            if not record.expected_chunk_ids:
                raise ValueError(f"positive sample has no expected chunks: {record.question}")
            if record.reference_answer == NEGATIVE_REFERENCE_ANSWER:
                raise ValueError(f"positive sample has negative reference: {record.question}")
            if len(record.expected_chunk_ids) != len(set(record.expected_chunk_ids)):
                raise ValueError(f"duplicate expected chunk ids: {record.question}")
            update = {
                "dataset_name": dataset_name,
                "created_by": created_by,
                "tags": list(dict.fromkeys([*record.tags, record.question_type])),
            }
        normalized.append(record.model_copy(update=update))

    if len({record.dataset_name for record in normalized}) != 1:
        raise ValueError("one import file must belong to exactly one dataset")
    return normalized


class EvalDataGenerator:
    """通过 LLM 网关生成单条评测样本，不直接写入数据库。"""

    def __init__(
        self,
        *,
        router: LLMRouter | None = None,
        provider: LLMProvider | None = None,
        max_retries: int = 1,
    ) -> None:
        self._router = router
        self._provider = provider
        self._max_retries = max_retries
        self._route: RoutedModel | None = None

    async def generate(
        self,
        *,
        dataset_name: str,
        question_type: QuestionType,
        evidence: Sequence[EvidenceChunk],
        existing_questions: Sequence[str],
        created_by: str,
    ) -> GeneratedEvalCase:
        if not evidence:
            raise ValueError("evidence must not be empty")

        route = self._get_route()
        validation_error: str | None = None
        normalized_existing = {question.strip().casefold() for question in existing_questions}
        prompt_evidence = [
            {
                "index": index,
                "document_name": chunk.document_name,
                "page_number": chunk.page_number,
                "heading_path": " > ".join(chunk.heading_path),
                "content": chunk.content,
            }
            for index, chunk in enumerate(evidence, start=1)
        ]

        for _ in range(self._max_retries + 1):
            result = await route.provider.chat(
                [
                    LLMMessage(
                        role="user",
                        content=render_evaluation_prompt(
                            "eval_data_generation.j2",
                            question_type=question_type,
                            evidence=prompt_evidence,
                            existing_questions=list(existing_questions)[-30:],
                            negative_reference_answer=NEGATIVE_REFERENCE_ANSWER,
                            validation_error=validation_error,
                        ),
                    )
                ],
                task=LLMTask.EVAL_DATA_GENERATION.value,
                temperature=0.4,
                max_tokens=1200,
            )
            try:
                payload = _GeneratedPayload.model_validate(parse_json_object(result.text))
                return self._build_case(
                    dataset_name=dataset_name,
                    question_type=question_type,
                    payload=payload,
                    evidence=evidence,
                    normalized_existing=normalized_existing,
                    created_by=created_by,
                )
            except (StructuredOutputError, ValidationError, ValueError) as exc:
                validation_error = str(exc)

        raise EvalDataGenerationError(
            f"model returned invalid eval data after {self._max_retries + 1} attempts: "
            f"{validation_error}"
        )

    def _get_route(self) -> RoutedModel:
        if self._route is not None:
            return self._route
        if self._provider is not None:
            self._route = RoutedModel(
                task=LLMTask.EVAL_DATA_GENERATION,
                alias="injected",
                provider_name="injected",
                model_name="injected",
                input_cost_per_million=0,
                output_cost_per_million=0,
                provider=self._provider,
            )
            return self._route
        router = self._router or create_default_router()
        self._route = router.resolve(LLMTask.EVAL_DATA_GENERATION)
        return self._route

    @staticmethod
    def _build_case(
        *,
        dataset_name: str,
        question_type: QuestionType,
        payload: _GeneratedPayload,
        evidence: Sequence[EvidenceChunk],
        normalized_existing: set[str],
        created_by: str,
    ) -> GeneratedEvalCase:
        question = payload.question.strip()
        if question.casefold() in normalized_existing:
            raise ValueError("generated question duplicates an existing question")

        if question_type == "out_of_kb":
            if payload.evidence_indexes:
                raise ValueError("out_of_kb sample must not reference evidence")
            return GeneratedEvalCase(
                dataset_name=dataset_name,
                question_type=question_type,
                question=question,
                reference_answer=NEGATIVE_REFERENCE_ANSWER,
                tags=[question_type, "negative"],
                created_by=created_by,
            )

        indexes = list(dict.fromkeys(payload.evidence_indexes))
        if not indexes or any(index < 1 or index > len(evidence) for index in indexes):
            raise ValueError(f"evidence indexes must be within 1..{len(evidence)}")
        selected = [evidence[index - 1] for index in indexes]
        if question_type == "multi_document" and len({chunk.document_id for chunk in selected}) < 2:
            raise ValueError("multi_document sample requires evidence from two documents")

        reference_answer = payload.reference_answer.strip()
        if reference_answer == NEGATIVE_REFERENCE_ANSWER:
            raise ValueError("positive sample cannot use the negative reference answer")
        return GeneratedEvalCase(
            dataset_name=dataset_name,
            question_type=question_type,
            question=question,
            reference_answer=reference_answer,
            evidence_chunks=[
                chunk.model_copy(update={"content": chunk.content[:1200]}) for chunk in selected
            ],
            expected_chunk_ids=[chunk.chunk_id for chunk in selected],
            tags=[question_type],
            created_by=created_by,
        )
