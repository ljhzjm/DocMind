import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import replace

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.llm import LLMMessage, LLMRouter, LLMTask, create_default_router
from app.llm.base import LLMProvider
from app.rag.parsing import StructuredOutputError, parse_json_object
from app.rag.prompts import render_prompt
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
    """根据配置返回 API LLM、透传或 bge-reranker 实现。"""
    if not settings.rerank_enabled or settings.rerank_provider == "passthrough":
        return PassthroughReranker()
    if settings.rerank_provider == "llm":
        return LLMRerankerProvider()
    if settings.rerank_provider == "bge":
        if not settings.rerank_base_url:
            raise RerankConfigurationError("RERANK_BASE_URL is required for bge")
        return BGERerankerProvider(
            base_url=settings.rerank_base_url,
            api_key=os.getenv(settings.rerank_api_key_env, ""),
            timeout_seconds=settings.rerank_timeout_seconds,
        )
    raise RerankConfigurationError(f"reranker '{settings.rerank_provider}' is not implemented")


class _RerankItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int
    relevance_score: float


class _RerankPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[_RerankItem]


class BGERerankerProvider(RerankProvider):
    """调用独立 bge-reranker HTTP 服务。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalHit],
        *,
        top_k: int,
    ) -> list[RetrievalHit]:
        if not candidates:
            return []
        response = await self._client.post(
            f"{self._base_url}/rerank",
            headers=self._headers,
            json={
                "query": query,
                "documents": [candidate.content for candidate in candidates],
                "top_n": top_k,
            },
        )
        response.raise_for_status()
        payload = _RerankPayload.model_validate(response.json())
        return [
            replace(
                candidates[item.index],
                score=item.relevance_score,
                sources=("rerank",),
            )
            for item in sorted(
                payload.results,
                key=lambda result: result.relevance_score,
                reverse=True,
            )[:top_k]
        ]

    async def aclose(self) -> None:
        await self._client.aclose()


class _LLMRerankItem(BaseModel):
    index: int = Field(ge=0)
    score: float = Field(ge=0, le=1)


class _LLMRerankPayload(BaseModel):
    results: list[_LLMRerankItem]


class LLMRerankerProvider(RerankProvider):
    """通过现有 LLM 网关对候选片段打相关性分数。"""

    def __init__(
        self,
        *,
        router: LLMRouter | None = None,
        provider: LLMProvider | None = None,
        max_retries: int = 1,
    ) -> None:
        self._router = router or create_default_router()
        self._provider = provider
        self._max_retries = max_retries

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalHit],
        *,
        top_k: int,
    ) -> list[RetrievalHit]:
        if not candidates:
            return []
        provider = self._provider or self._router.resolve(LLMTask.RERANK).provider
        candidate_payload = [
            {"index": index, "content": candidate.content[:1200]}
            for index, candidate in enumerate(candidates)
        ]
        validation_error: str | None = None
        for _ in range(self._max_retries + 1):
            result = await provider.chat(
                [
                    LLMMessage(
                        role="user",
                        content=render_prompt(
                            "rerank.j2",
                            query=query,
                            candidates=candidate_payload,
                        ),
                    )
                ],
                task=LLMTask.RERANK.value,
            )
            try:
                payload = _LLMRerankPayload.model_validate(parse_json_object(result.text))
                return self._apply_scores(candidates, payload, top_k=top_k)
            except (StructuredOutputError, ValidationError, ValueError) as exc:
                validation_error = str(exc)
        raise RerankConfigurationError(
            f"LLM reranker returned invalid data after {self._max_retries + 1} attempts: "
            f"{validation_error}"
        )

    @staticmethod
    def _apply_scores(
        candidates: Sequence[RetrievalHit],
        payload: _LLMRerankPayload,
        *,
        top_k: int,
    ) -> list[RetrievalHit]:
        scores = {item.index: item.score for item in payload.results}
        ranked = [
            replace(
                candidate,
                score=scores.get(index, 0.0),
                sources=("rerank",),
            )
            for index, candidate in enumerate(candidates)
        ]
        ranked.sort(key=lambda candidate: candidate.score, reverse=True)
        return ranked[:top_k]
