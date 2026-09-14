from dataclasses import dataclass, field
from uuid import UUID

from app.retrieval.types import SearchMode


@dataclass(frozen=True)
class EvalCase:
    id: UUID
    question: str
    reference_answer: str
    expected_chunk_ids: tuple[UUID, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalConfig:
    name: str
    mode: SearchMode
    top_k: int
    rerank: bool


@dataclass(frozen=True)
class CaseMetrics:
    question: str
    recall_at_5: float
    reciprocal_rank: float
    faithfulness: float
    answer_relevance: float
    ragas_faithfulness: float | None
    ragas_answer_relevance: float | None
    latency_ms: float
    first_token_latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    refused: bool
    error: str | None = None


@dataclass(frozen=True)
class ConfigMetrics:
    config: RetrievalConfig
    case_count: int
    recall_at_5: float
    mrr: float
    faithfulness: float
    answer_relevance: float
    ragas_faithfulness: float | None
    ragas_answer_relevance: float | None
    average_latency_ms: float
    average_first_token_latency_ms: float
    average_input_tokens: float
    average_output_tokens: float
    average_estimated_cost: float
    refusal_rate: float
    hallucination_risk: float
    cases: list[CaseMetrics] = field(default_factory=list)
