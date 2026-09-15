from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation_run import EvaluationRun


async def create_evaluation_run(
    session: AsyncSession,
    *,
    run_id: UUID | None = None,
    dataset_name: str,
    configs: list[dict[str, Any]],
    task_id: str,
    progress_total: int,
    results: list[dict[str, Any]] | None = None,
) -> EvaluationRun:
    run = EvaluationRun(
        id=run_id or uuid4(),
        dataset_name=dataset_name,
        configs=configs,
        task_id=task_id,
        progress_total=progress_total,
        results=results or [],
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


async def mark_evaluation_run_running(
    session: AsyncSession,
    run_id: UUID,
) -> bool:
    result = await session.execute(
        update(EvaluationRun)
        .where(
            EvaluationRun.id == run_id,
            EvaluationRun.status == "queued",
        )
        .values(
            status="running",
            started_at=datetime.now(UTC),
            error_message=None,
        )
        .returning(EvaluationRun.id)
    )
    await session.commit()
    return result.scalar_one_or_none() is not None


async def update_evaluation_run_progress(
    session: AsyncSession,
    run_id: UUID,
    *,
    completed: int,
    total: int,
    checkpoint: list[dict[str, Any]] | None = None,
) -> None:
    values: dict[str, Any] = {
        "progress_completed": max(0, completed),
        "progress_total": max(0, total),
    }
    if checkpoint is not None:
        values["checkpoint"] = checkpoint
    await session.execute(update(EvaluationRun).where(EvaluationRun.id == run_id).values(**values))
    await session.commit()


async def complete_evaluation_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    results: list[dict[str, Any]],
) -> None:
    await session.execute(
        update(EvaluationRun)
        .where(
            EvaluationRun.id == run_id,
            EvaluationRun.status == "running",
        )
        .values(
            status="completed",
            results=results,
            progress_completed=EvaluationRun.progress_total,
            completed_at=datetime.now(UTC),
            error_message=None,
        )
    )
    await session.commit()


async def fail_evaluation_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    error_message: str,
) -> None:
    await session.execute(
        update(EvaluationRun)
        .where(
            EvaluationRun.id == run_id,
            EvaluationRun.status.in_(("queued", "running")),
        )
        .values(
            status="failed",
            error_message=error_message[:2000],
            completed_at=datetime.now(UTC),
        )
    )
    await session.commit()


async def cancel_evaluation_run(
    session: AsyncSession,
    run_id: UUID,
) -> bool:
    result = await session.execute(
        update(EvaluationRun)
        .where(
            EvaluationRun.id == run_id,
            EvaluationRun.status.in_(("queued", "running")),
        )
        .values(
            status="cancelled",
            completed_at=datetime.now(UTC),
            error_message=None,
        )
        .returning(EvaluationRun.id)
    )
    await session.commit()
    return result.scalar_one_or_none() is not None


async def resume_evaluation_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    task_id: str,
) -> bool:
    result = await session.execute(
        update(EvaluationRun)
        .where(
            EvaluationRun.id == run_id,
            EvaluationRun.status.in_(("failed", "cancelled")),
        )
        .values(
            status="queued",
            task_id=task_id,
            attempt=EvaluationRun.attempt + 1,
            started_at=None,
            completed_at=None,
            error_message=None,
        )
        .returning(EvaluationRun.id)
    )
    await session.commit()
    return result.scalar_one_or_none() is not None
