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
    estimated_cost: float
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
    average_estimated_cost: float
    cases: list[CaseMetrics] = field(default_factory=list)
