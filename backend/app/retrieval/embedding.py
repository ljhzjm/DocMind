from abc import ABC, abstractmethod

from app.llm import LLMRouter, LLMTask, create_default_router


class EmbeddingError(RuntimeError):
    """Embedding 网关未返回可用向量。"""


class EmbeddingProvider(ABC):
    """检索层只依赖该抽象，方便切换到本地 bge-m3。"""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError


class LLMGatewayEmbeddingProvider(EmbeddingProvider):
    """默认通过 app.llm 路由调用 OpenAI 兼容 Embedding 接口。"""

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or create_default_router()

    async def embed_text(self, text: str) -> list[float]:
        route = self._router.resolve(LLMTask.EMBEDDING)
        result = await route.provider.embed([text], task=LLMTask.EMBEDDING.value)
        if not result.embeddings or len(result.embeddings[0]) != 1024:
            raise EmbeddingError("embedding provider must return one 1024-dim vector")
        return result.embeddings[0]
