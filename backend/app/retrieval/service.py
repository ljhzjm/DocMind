from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.bm25 import bm25_search
from app.retrieval.embedding import EmbeddingProvider, LLMGatewayEmbeddingProvider
from app.retrieval.fusion import rrf_fuse
from app.retrieval.types import RetrievalHit, SearchMode
from app.retrieval.vector import vector_search


class SearchService:
    """按 vector、BM25 或 hybrid 模式编排检索。"""

    def __init__(self, embedding_provider: EmbeddingProvider | None = None) -> None:
        self._embedding_provider = embedding_provider or LLMGatewayEmbeddingProvider()

    async def search(
        self,
        session: AsyncSession,
        *,
        query: str,
        mode: SearchMode,
        top_k: int,
    ) -> list[RetrievalHit]:
        if mode is SearchMode.VECTOR:
            return await vector_search(
                session,
                self._embedding_provider,
                query,
                top_k=top_k,
            )
        if mode is SearchMode.BM25:
            return await bm25_search(session, query, top_k=top_k)

        candidate_k = max(top_k * 3, top_k)
        vector_results = await vector_search(
            session,
            self._embedding_provider,
            query,
            top_k=candidate_k,
        )
        bm25_results = await bm25_search(session, query, top_k=candidate_k)
        return rrf_fuse(vector_results, bm25_results, top_k=top_k)
