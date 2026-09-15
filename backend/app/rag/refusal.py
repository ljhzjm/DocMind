from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.repositories.retrieval_thresholds import get_retrieval_threshold


def rerank_provider_key(settings: Settings, *, rerank_enabled: bool) -> str:
    """把实际生效的 reranker 配置转换成阈值表 key。"""
    if not rerank_enabled or not settings.rerank_enabled:
        return "none"
    if settings.rerank_provider == "passthrough":
        return "none"
    return settings.rerank_provider


async def get_effective_refusal_threshold(
    session: AsyncSession,
    settings: Settings,
    *,
    mode: str,
    top_k: int,
    rerank_enabled: bool,
) -> float:
    """优先使用离线校准阈值，缺失时回退全局配置。"""
    provider_key = rerank_provider_key(settings, rerank_enabled=rerank_enabled)
    threshold = await get_retrieval_threshold(
        session,
        mode=mode,
        top_k=top_k,
        rerank_provider=provider_key,
    )
    return threshold.threshold if threshold is not None else settings.rag_refusal_threshold
