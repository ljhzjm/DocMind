import json
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.llm.base import TokenUsage
from app.models.enums import UsageStep
from app.models.usage import UsageRecord

_TRACE_TTL_SECONDS = 24 * 60 * 60


class TraceRecorder:
    """将每个 RAG 环节写入 usage_records，并把调试快照写入 Redis。"""

    async def record(
        self,
        session: AsyncSession,
        *,
        trace_id: str,
        step: UsageStep,
        model: str,
        latency_ms: float,
        usage: TokenUsage | None = None,
    ) -> None:
        token_usage = usage or TokenUsage()
        session.add(
            UsageRecord(
                trace_id=trace_id,
                step=step,
                model=model,
                input_tokens=token_usage.input_tokens,
                output_tokens=token_usage.output_tokens,
                latency_ms=max(0, round(latency_ms)),
            )
        )
        await session.commit()

    async def store_snapshot(
        self,
        trace_id: str,
        payload: dict[str, Any],
        *,
        redis: Redis | None = None,
    ) -> None:
        client = redis or get_redis()
        await client.setex(
            f"trace:{trace_id}",
            _TRACE_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False, default=str),
        )

    async def get_snapshot(
        self,
        trace_id: str,
        *,
        redis: Redis | None = None,
    ) -> dict[str, Any] | None:
        client = redis or get_redis()
        value = await client.get(f"trace:{trace_id}")
        if value is None:
            return None
        parsed: object = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
