from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    FinishEvent,
    LLMConfigurationError,
    LLMMessage,
    LLMProvider,
    LLMStreamEvent,
    TokenUsage,
)
from app.llm.config import LLMConfig, ModelConfig, ProviderConfig, load_llm_config
from app.llm.router import LLMRouter, LLMTask


class StubProvider(LLMProvider):
    def chat_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        del messages, task, temperature, max_tokens

        async def events() -> AsyncIterator[LLMStreamEvent]:
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
        del messages, task, temperature, max_tokens
        return ChatResult(
            text="",
            usage=TokenUsage(),
            finish_reason="stop",
        )

    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: str | None = None,
    ) -> EmbeddingResult:
        del texts, task
        return EmbeddingResult(embeddings=[], usage=TokenUsage())


def stub_factory(
    provider_name: str,
    provider_config: ProviderConfig,
    alias: str,
    model_config: ModelConfig,
) -> LLMProvider:
    del provider_name, provider_config, alias, model_config
    return StubProvider()


def test_router_selects_cheap_and_strong_models_from_config(tmp_path: Path) -> None:
    config_path = tmp_path / "models.toml"
    config_path.write_text(
        """
[providers.fake]
base_url = "https://llm.example/v1"
api_key_env = "FAKE_API_KEY"

[models.cheap]
provider = "fake"
model = "cheap-model"

[models.strong]
provider = "fake"
model = "strong-model"

[routes]
intent_classification = "cheap"
query_rewrite = "cheap"
final_generation = "strong"
""".strip(),
        encoding="utf-8",
    )
    calls: list[tuple[str, str]] = []

    def factory(
        provider_name: str,
        provider_config: ProviderConfig,
        alias: str,
        model_config: ModelConfig,
    ) -> LLMProvider:
        del provider_name, provider_config
        calls.append((alias, model_config.model))
        return StubProvider()

    router = LLMRouter(load_llm_config(config_path), factory)
    intent = router.resolve(LLMTask.INTENT_CLASSIFICATION)
    rewrite = router.resolve(LLMTask.QUERY_REWRITE)
    final = router.resolve(LLMTask.FINAL_GENERATION)

    assert intent.model_name == "cheap-model"
    assert rewrite.model_name == "cheap-model"
    assert final.model_name == "strong-model"
    assert intent.provider is rewrite.provider
    assert calls == [("cheap", "cheap-model"), ("strong", "strong-model")]


def test_router_rejects_unconfigured_task() -> None:
    config = LLMConfig(
        providers={
            "fake": ProviderConfig(
                base_url="https://llm.example/v1",
                api_key_env="FAKE_API_KEY",
            )
        },
        models={
            "cheap": ModelConfig(provider="fake", model="cheap-model"),
        },
        routes={},
    )
    router = LLMRouter(config, stub_factory)

    with pytest.raises(LLMConfigurationError, match="no model route configured"):
        router.resolve(LLMTask.INTENT_CLASSIFICATION)
