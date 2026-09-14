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
        batch_size = route.max_batch_size or len(texts)
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            result = await route.provider.embed(batch, task=LLMTask.EMBEDDING.value)
            if len(result.embeddings) != len(batch):
                raise EmbeddingError("embedding provider returned an unexpected vector count")
            if any(len(vector) != 1024 for vector in result.embeddings):
                raise EmbeddingError("embedding provider must return 1024-dim vectors")
            embeddings.extend(result.embeddings)
        return embeddings
