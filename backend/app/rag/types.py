from dataclasses import dataclass

from pydantic import BaseModel, Field

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


@dataclass(frozen=True)
class AnswerDeltaEvent:
    delta: str


@dataclass(frozen=True)
class DoneEvent:
    citations: list[int]


@dataclass(frozen=True)
class ErrorEvent:
    message: str


RAGStreamEvent = RetrievalEvent | AnswerDeltaEvent | DoneEvent | ErrorEvent
