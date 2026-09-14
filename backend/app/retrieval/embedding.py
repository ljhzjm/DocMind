from abc import ABC, abstractmethod

from app.llm import LLMRouter, LLMTask, create_default_router


class EmbeddingError(RuntimeError):
    """Embedding 网关未返回可用向量。"""


class EmbeddingProvider(ABC):
    """检索层只依赖该抽象，方便切换到本地 bge-m3。"""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(text) for text in texts]


class LLMGatewayEmbeddingProvider(EmbeddingProvider):
    """默认通过 app.llm 路由调用 OpenAI 兼容 Embedding 接口。"""

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or create_default_router()

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        route = self._router.resolve(LLMTask.EMBEDDING)
        result = await route.provider.embed(texts, task=LLMTask.EMBEDDING.value)
        if len(result.embeddings) != len(texts):
            raise EmbeddingError("embedding provider returned an unexpected vector count")
        if any(len(vector) != 1024 for vector in result.embeddings):
            raise EmbeddingError("embedding provider must return 1024-dim vectors")
        return result.embeddings
