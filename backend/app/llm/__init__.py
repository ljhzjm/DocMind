"""Provider-neutral model gateway boundary.

All LLM and embedding calls must pass through this package.
"""

from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    FinishEvent,
    LLMConfigurationError,
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
from app.llm.router import LLMRouter, LLMTask, RoutedModel, create_default_router

__all__ = [
    "CallCostRecord",
    "ChatResult",
    "EmbeddingResult",
    "FinishEvent",
    "LLMConfigurationError",
    "LLMConfig",
    "LLMMessage",
    "LLMProvider",
    "LLMRouter",
    "LLMTask",
    "LLMStreamEvent",
    "LoggingCostRecorder",
    "ModelConfig",
    "OpenAICompatibleProvider",
    "RoutedModel",
    "ProviderConfig",
    "TextDeltaEvent",
    "TokenUsage",
    "UsageEvent",
    "create_default_router",
    "load_llm_config",
]
