from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class TextDeltaEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["text_delta"] = "text_delta"
    text: str
    request_id: str | None = None


class UsageEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["usage"] = "usage"
    usage: TokenUsage
    request_id: str | None = None


class FinishEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["finish"] = "finish"
    finish_reason: str | None
    usage: TokenUsage | None = None
    request_id: str | None = None


LLMStreamEvent = TextDeltaEvent | UsageEvent | FinishEvent


class ChatResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    usage: TokenUsage
    finish_reason: str | None
    request_id: str | None = None


class EmbeddingResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    embeddings: list[list[float]]
    usage: TokenUsage
    request_id: str | None = None


class LLMError(Exception):
    """Base class for gateway failures safe to handle at the service boundary."""


class LLMConfigurationError(LLMError):
    """Raised when a configured model route cannot be constructed."""


class LLMHTTPError(LLMError):
    def __init__(self, status_code: int, request_id: str | None = None) -> None:
        super().__init__(f"LLM provider returned HTTP {status_code}")
        self.status_code = status_code
        self.request_id = request_id


class LLMResponseError(LLMError):
    """Raised when a provider response does not match the gateway contract."""


class LLMRetryExhausted(LLMError):
    def __init__(self, attempts: int, request_id: str | None = None) -> None:
        super().__init__(f"LLM request failed after {attempts} attempts")
        self.attempts = attempts
        self.request_id = request_id


class LLMProvider(ABC):
    """Provider-neutral interface implemented only inside app.llm."""

    @abstractmethod
    def chat_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        raise NotImplementedError

    @abstractmethod
    async def chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        raise NotImplementedError

    @abstractmethod
    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: str | None = None,
    ) -> EmbeddingResult:
        raise NotImplementedError
