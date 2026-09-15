from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.retrieval_threshold import RetrievalThreshold


async def get_retrieval_threshold(
    session: AsyncSession,
    *,
    mode: str,
    top_k: int,
    rerank_provider: str,
) -> RetrievalThreshold | None:
    return cast(
        RetrievalThreshold | None,
        await session.scalar(
            select(RetrievalThreshold).where(
                RetrievalThreshold.mode == mode,
                RetrievalThreshold.top_k == top_k,
                RetrievalThreshold.rerank_provider == rerank_provider,
            )
        ),
    )


async def list_retrieval_thresholds(
    session: AsyncSession,
) -> list[RetrievalThreshold]:
    result = await session.scalars(
        select(RetrievalThreshold).order_by(
            RetrievalThreshold.mode,
            RetrievalThreshold.top_k,
            RetrievalThreshold.rerank_provider,
        )
    )
    return list(result.all())


async def upsert_retrieval_threshold(
    session: AsyncSession,
    *,
    mode: str,
    top_k: int,
    rerank_provider: str,
    threshold: float,
    sample_count: int,
    metrics: dict[str, Any],
) -> RetrievalThreshold:
    record = await get_retrieval_threshold(
        session,
        mode=mode,
        top_k=top_k,
        rerank_provider=rerank_provider,
    )
    if record is None:
        record = RetrievalThreshold(
            mode=mode,
            top_k=top_k,
            rerank_provider=rerank_provider,
            threshold=threshold,
            sample_count=sample_count,
            metrics=metrics,
        )
        session.add(record)
    else:
        record.threshold = threshold
        record.sample_count = sample_count
        record.metrics = metrics
        record.created_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(record)
    return record
