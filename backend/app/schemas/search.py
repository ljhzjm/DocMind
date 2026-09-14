from uuid import UUID

from pydantic import BaseModel, Field

from app.retrieval.types import SearchMode


class SearchResultResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    content: str
    document_name: str
    page_number: int | None
    heading_path: list[str]
    score: float
    sources: list[str]


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    top_k: int = Field(ge=1)
    results: list[SearchResultResponse]


class StepResultsResponse(BaseModel):
    latency_ms: float
    error: str | None = None
    results: list[SearchResultResponse]


class RewriteDebugResponse(BaseModel):
    query: str
    keywords: list[str]
    retrieval_query: str
    latency_ms: float


class SearchDebugResponse(BaseModel):
    query: str
    top_k: int = Field(ge=1)
    rewrite: RewriteDebugResponse
    vector: StepResultsResponse
    bm25: StepResultsResponse
    fusion: StepResultsResponse
    rerank: StepResultsResponse


class UsageRecordResponse(BaseModel):
    step: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    created_at: str


class TraceReplayResponse(BaseModel):
    trace_id: str
    snapshot: dict[str, object] | None
    usage_records: list[UsageRecordResponse]
