from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_ROOT / ".env"


def load_environment_file(path: Path) -> None:
    """显式加载 .env，使供应商密钥也能被 os.getenv() 读取。"""
    load_dotenv(path, override=False)


load_environment_file(_ENV_FILE)


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
    parent_child_enabled: bool = True
    parent_chunk_size: int = 2048
    embedding_batch_size: int = 10
    ocr_enabled: bool = False
    ocr_language: str = "chi_sim+eng"
    retrieval_top_k: int = 10
    rag_candidate_top_k: int = 20
    rag_context_top_k: int = 5
    rag_refusal_threshold: float = 0.0
    rag_retrieval_mode: str = "hybrid"
    rerank_enabled: bool = True
    rerank_provider: str = "llm"
    rerank_base_url: str = ""
    rerank_api_key_env: str = "RERANK_API_KEY"
    rerank_timeout_seconds: float = 30.0
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    answer_cache_enabled: bool = True
    answer_cache_ttl_seconds: int = 3600
    rate_limit_enabled: bool = True
    rate_limit_capacity: int = 60
    rate_limit_refill_per_second: float = 1.0
    log_level: str = "INFO"
    cors_origins: str = "http://127.0.0.1:15173,http://localhost:15173"
    require_api_key: bool = False
    api_keys: str = ""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_cors_origins(self) -> list[str]:
        """返回 CORS 白名单列表。"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_api_keys(self) -> frozenset[str]:
        """返回允许访问 API 的密钥集合，真实值只从环境变量读取。"""
        return frozenset(key.strip() for key in self.api_keys.split(",") if key.strip())

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
        if self.embedding_batch_size <= 0:
            raise ValueError("embedding_batch_size must be positive")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be between 0 and chunk_size")
        if self.parent_chunk_size < self.chunk_size:
            raise ValueError("parent_chunk_size must be >= chunk_size")
        if self.rag_candidate_top_k <= 0 or self.rag_context_top_k <= 0:
            raise ValueError("RAG top_k values must be positive")
        if self.rag_refusal_threshold < 0:
            raise ValueError("rag_refusal_threshold must not be negative")
        if self.retrieval_top_k <= 0:
            raise ValueError("retrieval_top_k must be positive")
        if self.answer_cache_ttl_seconds <= 0:
            raise ValueError("answer_cache_ttl_seconds must be positive")
        if self.rate_limit_capacity <= 0:
            raise ValueError("rate_limit_capacity must be positive")
        if self.rate_limit_refill_per_second <= 0:
            raise ValueError("rate_limit_refill_per_second must be positive")
        if self.max_upload_size_bytes <= 0:
            raise ValueError("max_upload_size_bytes must be positive")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
