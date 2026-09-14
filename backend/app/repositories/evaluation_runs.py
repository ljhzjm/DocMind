from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation_run import EvaluationRun


async def create_evaluation_run(
    session: AsyncSession,
    *,
    dataset_name: str,
    configs: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> EvaluationRun:
    run = EvaluationRun(
        dataset_name=dataset_name,
        configs=configs,
        results=results,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def list_evaluation_runs(
    session: AsyncSession,
    *,
    limit: int = 50,
) -> list[EvaluationRun]:
    result = await session.scalars(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(limit)
    )
    return list(result.all())


async def get_evaluation_run(
    session: AsyncSession,
    run_id: UUID,
) -> EvaluationRun | None:
    return await session.get(EvaluationRun, run_id)
