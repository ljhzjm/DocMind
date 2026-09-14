from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.core.config import Settings
from app.retrieval.types import RetrievalHit


class RerankConfigurationError(RuntimeError):
    """配置指定的 reranker 尚未接入。"""


class RerankProvider(ABC):
    """重排接口；bge-reranker 后续实现该接口即可接入。"""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalHit],
        *,
        top_k: int,
    ) -> list[RetrievalHit]:
        raise NotImplementedError


class PassthroughReranker(RerankProvider):
    """阶段一默认实现：保持原排名并截断 top_k。"""

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalHit],
        *,
        top_k: int,
    ) -> list[RetrievalHit]:
        del query
        return list(candidates[:top_k])


def create_reranker(settings: Settings) -> RerankProvider:
    """根据配置返回重排实现，为 bge-reranker 保留明确扩展点。"""
    if not settings.rerank_enabled or settings.rerank_provider == "passthrough":
        return PassthroughReranker()
    raise RerankConfigurationError(f"reranker '{settings.rerank_provider}' is not implemented")
