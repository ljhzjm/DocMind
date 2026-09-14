import logging
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.llm.base import TokenUsage

logger = logging.getLogger(__name__)


class CallCostRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    provider: str
    model: str
    task: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0, ge=0)
    finish_reason: str | None = None
    success: bool = True


class CostRecorder(Protocol):
    def record(self, record: CallCostRecord) -> None: ...


class LoggingCostRecorder:
    """Writes usage metadata to structured logs until persistence is added."""

    def record(self, record: CallCostRecord) -> None:
        logger.info(
            "llm_call",
            extra={"llm_call": record.model_dump(mode="json")},
        )


class CallTimer:
    def __init__(self) -> None:
        self._started_at = perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return round((perf_counter() - self._started_at) * 1000, 3)


def usage_from_counts(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> TokenUsage:
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def resolve_request_id(request_id: str | None) -> str:
    return request_id or uuid4().hex


def calculate_token_cost(
    usage: TokenUsage,
    *,
    input_cost_per_million: float,
    output_cost_per_million: float,
) -> float:
    """按百万 token 单价估算调用成本，单位与配置一致。"""
    return (
        usage.input_tokens * input_cost_per_million + usage.output_tokens * output_cost_per_million
    ) / 1_000_000
