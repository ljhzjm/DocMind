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
from app.llm.config import LLMConfig, ModelConfig, ProviderConfig, load_llm_config
from app.llm.cost import CallCostRecord, LoggingCostRecorder
from app.llm.openai_compat import OpenAICompatibleProvider

__all__ = [
    "CallCostRecord",
    "ChatResult",
    "EmbeddingResult",
    "FinishEvent",
    "LLMConfig",
    "LLMMessage",
    "LLMProvider",
    "LLMStreamEvent",
    "LoggingCostRecorder",
    "ModelConfig",
    "OpenAICompatibleProvider",
    "ProviderConfig",
    "TextDeltaEvent",
    "TokenUsage",
    "UsageEvent",
    "load_llm_config",
]
