from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.retrieval.types import RetrievalHit


class RAGAnswer(BaseModel):
    """模型必须返回的结构化答案。"""

    answer: str = Field(min_length=1)
    citations: list[int]


@dataclass(frozen=True)
class RetrievalEvent:
    latency_ms: float
    chunk_count: int


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


@dataclass(frozen=True)
class RAGContext:
    citation_number: int
    hit: RetrievalHit
