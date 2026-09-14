"""Provider-neutral model gateway boundary.

All LLM and embedding calls must pass through this package.
"""

from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    FinishEvent,
    LLMMessage,
    LLMProvider,
    LLMStreamEvent,
    TextDeltaEvent,
    TokenUsage,
    UsageEvent,
)
from app.llm.cost import CallCostRecord, LoggingCostRecorder

__all__ = [
    "CallCostRecord",
    "ChatResult",
    "EmbeddingResult",
    "FinishEvent",
    "LLMMessage",
    "LLMProvider",
    "LLMStreamEvent",
    "LoggingCostRecorder",
    "TextDeltaEvent",
    "TokenUsage",
    "UsageEvent",
]
