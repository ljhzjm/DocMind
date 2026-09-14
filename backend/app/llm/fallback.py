import logging
from collections.abc import AsyncIterator, Sequence

from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    LLMConfigurationError,
    LLMHTTPError,
    LLMMessage,
    LLMProvider,
    LLMRetryExhausted,
    LLMStreamEvent,
)

logger = logging.getLogger(__name__)


class FallbackLLMProvider(LLMProvider):
    """主模型超时或返回 5xx 时，按配置切换备用模型。"""

    def __init__(self, providers: Sequence[tuple[str, LLMProvider]]) -> None:
        if not providers:
            raise LLMConfigurationError("fallback provider requires at least one model")
        self._providers = list(providers)

    async def chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        for index, (alias, provider) in enumerate(self._providers):
            try:
                return await provider.chat(
                    messages,
                    task=task,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except (LLMConfigurationError, LLMRetryExhausted, LLMHTTPError) as exc:
                self._handle_failure(alias, index, exc)
        raise LLMConfigurationError("all fallback providers failed")

    async def chat_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        for index, (alias, provider) in enumerate(self._providers):
            emitted = False
            try:
                async for event in provider.chat_stream(
                    messages,
                    task=task,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    emitted = True
                    yield event
                return
            except (LLMConfigurationError, LLMRetryExhausted, LLMHTTPError) as exc:
                if emitted:
                    raise
                self._handle_failure(alias, index, exc)

    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: str | None = None,
    ) -> EmbeddingResult:
        for index, (alias, provider) in enumerate(self._providers):
            try:
                return await provider.embed(texts, task=task)
            except (LLMConfigurationError, LLMRetryExhausted, LLMHTTPError) as exc:
                self._handle_failure(alias, index, exc)
        raise LLMConfigurationError("all fallback providers failed")

    def _handle_failure(self, alias: str, index: int, exc: Exception) -> None:
        if not self._should_fallback(exc):
            raise exc
        logger.warning(
            "llm_fallback",
            extra={
                "failed_alias": alias,
                "fallback_index": index,
                "error_type": type(exc).__name__,
                "status_code": getattr(exc, "status_code", None),
            },
        )

    @staticmethod
    def _should_fallback(exc: Exception) -> bool:
        if isinstance(exc, (LLMConfigurationError, LLMRetryExhausted)):
            return True
        return isinstance(exc, LLMHTTPError) and exc.status_code >= 500
