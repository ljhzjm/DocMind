import tomllib
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path(__file__).with_name("models.toml")


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str = Field(min_length=1)
    api_key_env: str = Field(min_length=1)
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=0.5, ge=0, le=30)
    default_headers: dict[str, str] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    fallbacks: list[str] = Field(default_factory=list)
    stream_include_usage: bool = False
    response_format_json: bool = False
    input_cost_per_million: float = Field(default=0.0, ge=0)
    output_cost_per_million: float = Field(default=0.0, ge=0)


class LLMConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    providers: dict[str, ProviderConfig]
    models: dict[str, ModelConfig]
    routes: dict[str, str]

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        for alias, model in self.models.items():
            if model.provider not in self.providers:
                raise ValueError(f"model '{alias}' references unknown provider")

        for alias, model in self.models.items():
            for fallback in model.fallbacks:
                if fallback not in self.models:
                    raise ValueError(f"model '{alias}' references unknown fallback '{fallback}'")
        for task, alias in self.routes.items():
            if alias not in self.models:
                raise ValueError(f"route '{task}' references unknown model")

        return self


def load_llm_config(path: str | Path | None = None) -> LLMConfig:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with config_path.open("rb") as config_file:
        payload: dict[str, Any] = tomllib.load(config_file)
    return LLMConfig.model_validate(payload)
