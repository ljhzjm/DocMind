from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import UsageRecord


async def list_usage_records(
    session: AsyncSession,
    trace_id: str,
) -> list[UsageRecord]:
    result = await session.scalars(
        select(UsageRecord)
        .where(UsageRecord.trace_id == trace_id)
        .order_by(UsageRecord.created_at, UsageRecord.id)
    )
    return list(result.all())
