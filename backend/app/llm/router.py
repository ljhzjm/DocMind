from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import get_settings
from app.llm.base import LLMConfigurationError, LLMProvider
from app.llm.config import LLMConfig, ModelConfig, ProviderConfig, load_llm_config
from app.llm.fallback import FallbackLLMProvider
from app.llm.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class LLMTask(StrEnum):
    INTENT_CLASSIFICATION = "intent_classification"
    QUERY_REWRITE = "query_rewrite"
    FINAL_GENERATION = "final_generation"
    EVAL_DATA_GENERATION = "eval_data_generation"
    RERANK = "rerank"
    EMBEDDING = "embedding"
    EVALUATION_JUDGE = "evaluation_judge"


ProviderFactory = Callable[
    [str, ProviderConfig, str, ModelConfig],
    LLMProvider,
]


@dataclass(frozen=True)
class RoutedModel:
    task: LLMTask
    alias: str
    provider_name: str
    model_name: str
    input_cost_per_million: float
    output_cost_per_million: float
    provider: LLMProvider
    max_batch_size: int | None = None


class LLMRouter:
    def __init__(
        self,
        config: LLMConfig,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        self._config = config
        self._provider_factory = provider_factory or create_openai_provider
        self._providers: dict[str, LLMProvider] = {}

    def _get_provider(self, alias: str) -> LLMProvider:
        cached = self._providers.get(alias)
        if cached is not None:
            return cached
        model_config = self._config.models[alias]
        provider_config = self._config.providers[model_config.provider]
        provider = self._provider_factory(
            model_config.provider,
            provider_config,
            alias,
            model_config,
        )
        self._providers[alias] = provider
        return provider

    def resolve(self, task: LLMTask) -> RoutedModel:
        task_key = task.value
        alias = self._config.routes.get(task_key)
        if alias is None:
            raise LLMConfigurationError(f"no model route configured for task '{task_key}'")

        model_config = self._config.models[alias]
        provider_entries = [
            (alias, self._get_provider(alias)),
            *[(fallback, self._get_provider(fallback)) for fallback in model_config.fallbacks],
        ]
        provider: LLMProvider
        if len(provider_entries) == 1:
            provider = provider_entries[0][1]
        else:
            provider = FallbackLLMProvider(provider_entries)

        return RoutedModel(
            task=task,
            alias=alias,
            provider_name=model_config.provider,
            model_name=model_config.model,
            input_cost_per_million=model_config.input_cost_per_million,
            output_cost_per_million=model_config.output_cost_per_million,
            provider=provider,
            max_batch_size=model_config.max_batch_size,
        )


def create_openai_provider(
    provider_name: str,
    provider_config: ProviderConfig,
    alias: str,
    model_config: ModelConfig,
) -> LLMProvider:
    del alias
    api_key = os.getenv(provider_config.api_key_env, "")
    if not api_key:
        raise LLMConfigurationError(
            f"environment variable '{provider_config.api_key_env}' is not set"
        )
    return OpenAICompatibleProvider(
        provider_name=provider_name,
        base_url=provider_config.base_url,
        api_key=api_key,
        model=model_config.model,
        timeout_seconds=provider_config.timeout_seconds,
        max_retries=provider_config.max_retries,
        retry_backoff_seconds=provider_config.retry_backoff_seconds,
        stream_include_usage=model_config.stream_include_usage,
        response_format_json=model_config.response_format_json,
        default_headers=provider_config.default_headers,
    )


def create_default_router(config: LLMConfig | None = None) -> LLMRouter:
    settings = get_settings()
    llm_config = config or load_llm_config(settings.llm_config_path or None)
    return LLMRouter(llm_config)
