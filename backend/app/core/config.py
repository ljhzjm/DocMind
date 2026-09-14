from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DocMind API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = ""
    llm_config_path: str = ""
    redis_url: str = ""
    upload_dir: Path = Path("storage/uploads")
    max_upload_size_bytes: int = 20 * 1024 * 1024
    allowed_upload_extensions: str = ".pdf,.md,.markdown"
    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 10
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_extensions(self) -> frozenset[str]:
        """返回统一为小写的上传扩展名白名单。"""
        return frozenset(
            extension.strip().lower()
            for extension in self.allowed_upload_extensions.split(",")
            if extension.strip()
        )

    @model_validator(mode="after")
    def validate_chunk_configuration(self) -> Self:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be between 0 and chunk_size")
        if self.retrieval_top_k <= 0:
            raise ValueError("retrieval_top_k must be positive")
        if self.max_upload_size_bytes <= 0:
            raise ValueError("max_upload_size_bytes must be positive")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
