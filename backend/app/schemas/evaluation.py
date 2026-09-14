from uuid import UUID

from pydantic import BaseModel, Field

from app.retrieval.types import SearchMode


class EvalDatasetSummary(BaseModel):
    dataset_name: str
    case_count: int


class EvalCaseResponse(BaseModel):
    id: UUID
    question: str
    reference_answer: str
    expected_chunk_ids: list[UUID]
    tags: list[str]
    created_by: str


class EvalCaseCreateRequest(BaseModel):
    question: str = Field(min_length=1)
    reference_answer: str = Field(min_length=1)
    expected_chunk_ids: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_by: str = Field(min_length=1, max_length=255)


class RetrievalConfigRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    mode: SearchMode
    top_k: int = Field(default=5, ge=1, le=50)
    rerank: bool = False


class EvalRunRequest(BaseModel):
    dataset_name: str = Field(min_length=1)
    configs: list[RetrievalConfigRequest] = Field(min_length=1, max_length=8)


class CaseMetricsResponse(BaseModel):
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
    error: str | None


class ConfigMetricsResponse(BaseModel):
    name: str
    mode: SearchMode
    top_k: int
    rerank: bool
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
    cases: list[CaseMetricsResponse]


class EvalRunResponse(BaseModel):
    run_id: UUID
    dataset_name: str
    results: list[ConfigMetricsResponse]


class EvaluationRunSummary(BaseModel):
    run_id: UUID
    dataset_name: str
    created_at: str
