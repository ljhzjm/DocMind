from collections.abc import AsyncIterator, Sequence

import pytest
from app.cache.answer_cache import cache_key, normalize_query
from app.core.config import Settings
from app.core.rate_limit import TokenBucketRateLimiter
from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    LLMHTTPError,
    LLMMessage,
    LLMProvider,
    LLMRetryExhausted,
    LLMStreamEvent,
    TokenUsage,
)
from app.llm.fallback import FallbackLLMProvider


class StaticProvider(LLMProvider):
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def chat_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        raise NotImplementedError

    async def chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        del messages, task, temperature, max_tokens
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ChatResult(
            text="fallback-ok",
            usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
            finish_reason="stop",
        )

    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: str | None = None,
    ) -> EmbeddingResult:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_fallback_provider_switches_after_retry_exhausted() -> None:
    primary = StaticProvider(error=LLMRetryExhausted(3))
    fallback = StaticProvider()
    provider = FallbackLLMProvider([("primary", primary), ("backup", fallback)])

    result = await provider.chat([LLMMessage(role="user", content="hello")])

    assert result.text == "fallback-ok"
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_fallback_provider_does_not_switch_on_client_error() -> None:
    primary = StaticProvider(error=LLMHTTPError(400))
    fallback = StaticProvider()
    provider = FallbackLLMProvider([("primary", primary), ("backup", fallback)])

    with pytest.raises(LLMHTTPError):
        await provider.chat([LLMMessage(role="user", content="hello")])

    assert fallback.calls == 0


def test_cache_key_normalizes_query() -> None:
    assert normalize_query("  DocMind   是什么？ ") == "docmind 是什么？"
    assert cache_key(
        query="DocMind 是什么？",
        knowledge_base_version="v1",
        retrieval_config="hybrid:5",
    ) == cache_key(
        query=" docmind   是什么？ ",
        knowledge_base_version="v1",
        retrieval_config="hybrid:5",
    )


class ScriptedRedis:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    async def eval(
        self,
        script: str,
        numkeys: int,
        *args: str,
    ) -> object:
        del script, numkeys, args
        return self.values.pop(0)


@pytest.mark.asyncio
async def test_token_bucket_returns_retry_after_when_limited() -> None:
    limiter = TokenBucketRateLimiter(
        redis=ScriptedRedis([[1, 0], [0, 1500]]),  # type: ignore[arg-type]
        settings=Settings(
            rate_limit_capacity=10,
            rate_limit_refill_per_second=1,
        ),
    )

    first = await limiter.check("ip:session")
    second = await limiter.check("ip:session")

    assert first.allowed is True
    assert second.allowed is False
    assert second.retry_after_seconds == 2


def test_json_log_formatter_injects_request_id() -> None:
    import json
    import logging

    from app.observability.context import request_id_context
    from app.observability.logging import JsonFormatter

    token = request_id_context.set("request-test")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_context.reset(token)

    assert payload["request_id"] == "request-test"
