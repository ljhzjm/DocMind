import logging
from collections.abc import AsyncIterator, Sequence
from typing import cast

import pytest
from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    FinishEvent,
    LLMMessage,
    LLMProvider,
    LLMStreamEvent,
    TextDeltaEvent,
    TokenUsage,
)
from app.llm.config import LLMConfig, ModelConfig, ProviderConfig
from app.llm.cost import CallCostRecord, LoggingCostRecorder, usage_from_counts
from app.llm.router import LLMRouter
from app.retrieval.embedding import LLMGatewayEmbeddingProvider


class StubProvider(LLMProvider):
    def chat_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        async def events() -> AsyncIterator[LLMStreamEvent]:
            yield TextDeltaEvent(text=messages[0].content)
            yield FinishEvent(finish_reason="stop")

        return events()

    async def chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        return ChatResult(
            text=messages[0].content,
            usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
            finish_reason="stop",
        )

    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: str | None = None,
    ) -> EmbeddingResult:
        return EmbeddingResult(
            embeddings=[[float(len(text))] for text in texts],
            usage=TokenUsage(input_tokens=len(texts), total_tokens=len(texts)),
        )


class BatchTrackingProvider(StubProvider):
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: str | None = None,
    ) -> EmbeddingResult:
        del task
        self.batch_sizes.append(len(texts))
        return EmbeddingResult(
            embeddings=[[0.0] * 1024 for _ in texts],
            usage=TokenUsage(input_tokens=len(texts), total_tokens=len(texts)),
        )


def test_usage_from_counts_sets_total() -> None:
    usage = usage_from_counts(input_tokens=7, output_tokens=3)

    assert usage.total_tokens == 10


def test_logging_cost_recorder_writes_usage_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    record = CallCostRecord(
        request_id="req-1",
        provider="openai_compat",
        model="cheap-model",
        task="intent_classification",
        input_tokens=12,
        output_tokens=3,
        duration_ms=42.5,
        finish_reason="stop",
    )

    with caplog.at_level(logging.INFO):
        LoggingCostRecorder().record(record)

    log_data = cast(dict[str, object], caplog.records[0].__dict__["llm_call"])
    assert log_data["request_id"] == "req-1"
    assert log_data["input_tokens"] == 12
    assert log_data["output_tokens"] == 3


@pytest.mark.asyncio
async def test_embedding_gateway_splits_provider_batches() -> None:
    provider = BatchTrackingProvider()
    router = LLMRouter(
        LLMConfig(
            providers={
                "fake": ProviderConfig(
                    base_url="https://llm.example/v1",
                    api_key_env="FAKE_API_KEY",
                )
            },
            models={
                "embedding": ModelConfig(
                    provider="fake",
                    model="text-embedding-v3",
                    max_batch_size=10,
                )
            },
            routes={"embedding": "embedding"},
        ),
        lambda *_args: provider,
    )

    vectors = await LLMGatewayEmbeddingProvider(router=router).embed_texts(
        [f"text-{index}" for index in range(11)]
    )

    assert len(vectors) == 11
    assert provider.batch_sizes == [10, 1]
