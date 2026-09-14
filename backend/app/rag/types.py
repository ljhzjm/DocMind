from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.llm.base import TokenUsage
from app.retrieval.types import RetrievalHit


class CitationValidationError(ValueError):
    """引用编号超出本次检索片段范围。"""


class RAGAnswer(BaseModel):
    """模型必须返回的结构化答案。"""

    answer: str = Field(min_length=1)
    citations: list[int]


@dataclass(frozen=True)
class RAGContext:
    citation_number: int
    hit: RetrievalHit


@dataclass(frozen=True)
class RetrievalEvent:
    latency_ms: float
    chunk_count: int
    contexts: tuple[RAGContext, ...] = ()
    trace_id: str | None = None
    cached: bool = False


@dataclass(frozen=True)
class AnswerDeltaEvent:
    delta: str


@dataclass(frozen=True)
class DoneEvent:
    citations: list[int]
    trace_id: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    model_name: str = ""
    estimated_cost: float = 0.0


@dataclass(frozen=True)
class ErrorEvent:
    message: str
    trace_id: str | None = None


RAGStreamEvent = RetrievalEvent | AnswerDeltaEvent | DoneEvent | ErrorEvent


@dataclass(frozen=True)
class GenerationOutcome:
    answer: RAGAnswer
    usage: TokenUsage
    model_name: str
    estimated_cost: float
