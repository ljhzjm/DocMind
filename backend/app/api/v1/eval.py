import logging
from typing import Annotated
from uuid import UUID, uuid4

from celery.exceptions import CeleryError
from fastapi import APIRouter, Depends, HTTPException, status
from kombu.exceptions import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.eval_dataset import EvalDatasetItem
from app.models.evaluation_run import EvaluationRun
from app.repositories.eval import (
    create_eval_case,
    list_eval_cases,
    list_eval_dataset_summaries,
)
from app.repositories.evaluation_runs import (
    cancel_evaluation_run,
    create_evaluation_run,
    fail_evaluation_run,
    get_evaluation_run,
    list_evaluation_runs,
    resume_evaluation_run,
)
from app.schemas.evaluation import (
    EvalCaseCreateRequest,
    EvalCaseResponse,
    EvalDatasetSummary,
    EvalRunRequest,
    EvalRunResponse,
    EvaluationRunAcceptedResponse,
    EvaluationRunSummary,
)
from app.workers.celery_app import celery_app
from app.workers.tasks import run_evaluation_task

router = APIRouter(prefix="/eval", tags=["evaluation"])
logger = logging.getLogger(__name__)


@router.get("/datasets", response_model=list[EvalDatasetSummary])
async def get_datasets(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[EvalDatasetSummary]:
    summaries = await list_eval_dataset_summaries(session)
    return [EvalDatasetSummary(dataset_name=name, case_count=count) for name, count in summaries]


@router.get("/datasets/{dataset_name}", response_model=list[EvalCaseResponse])
async def get_dataset_cases(
    dataset_name: str,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[EvalCaseResponse]:
    cases = await list_eval_cases(session, dataset_name)
    return [_case_response(case) for case in cases]


@router.post(
    "/datasets/{dataset_name}/items",
    response_model=EvalCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_dataset_case(
    dataset_name: str,
    request: EvalCaseCreateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EvalCaseResponse:
    case = await create_eval_case(
        session,
        dataset_name=dataset_name,
        question=request.question,
        reference_answer=request.reference_answer,
        expected_chunk_ids=request.expected_chunk_ids,
        tags=request.tags,
        created_by=request.created_by,
    )
    return _case_response(case)


@router.post(
    "/run",
    response_model=EvaluationRunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_evaluation(
    request: EvalRunRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EvaluationRunAcceptedResponse:
    """创建评测记录并立即返回 Celery 任务，不等待评测完成。"""
    stored_cases = await list_eval_cases(session, request.dataset_name)
    if not stored_cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evaluation dataset not found",
        )

    run_id = uuid4()
    task_id = f"evaluation-{run_id}"
    progress_total = len(stored_cases) * len(request.configs)
    run = await create_evaluation_run(
        session,
        run_id=run_id,
        dataset_name=request.dataset_name,
        task_id=task_id,
        progress_total=progress_total,
        configs=[config.model_dump(mode="json") for config in request.configs],
    )
    try:
        run_evaluation_task.apply_async(
            args=[str(run.id)],
            task_id=task_id,
        )
    except (CeleryError, OperationalError, OSError) as exc:
        await fail_evaluation_run(
            session,
            run.id,
            error_message="evaluation task could not be queued",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="evaluation task could not be queued",
        ) from exc

    return EvaluationRunAcceptedResponse(
        run_id=run.id,
        dataset_name=run.dataset_name,
        task_id=task_id,
        status="queued",
        attempt=run.attempt,
        progress_completed=0,
        progress_total=progress_total,
    )


def _case_response(case: EvalDatasetItem) -> EvalCaseResponse:
    return EvalCaseResponse(
        id=case.id,
        question=case.question,
        reference_answer=case.reference_answer,
        expected_chunk_ids=list(case.expected_chunk_ids),
        tags=list(case.tags),
        created_by=case.created_by,
    )


@router.get("/runs", response_model=list[EvaluationRunSummary])
async def get_evaluation_runs(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[EvaluationRunSummary]:
    runs = await list_evaluation_runs(session)
    return [
        EvaluationRunSummary(
            run_id=run.id,
            dataset_name=run.dataset_name,
            status=run.status,
            attempt=run.attempt,
            progress_completed=run.progress_completed,
            progress_total=run.progress_total,
            created_at=run.created_at.isoformat(),
        )
        for run in runs
    ]


@router.get("/runs/{run_id}", response_model=EvalRunResponse)
async def get_evaluation_run_detail(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EvalRunResponse:
    run = await get_evaluation_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    return _run_response(run)


@router.post("/runs/{run_id}/cancel", response_model=EvalRunResponse)
async def cancel_evaluation_run_endpoint(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EvalRunResponse:
    """取消 queued/running 评测，并尽力终止正在执行的 Celery 任务。"""
    run = await get_evaluation_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    if run.status == "cancelled":
        return _run_response(run)
    if run.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="evaluation run cannot be cancelled")

    terminate = run.status == "running"
    await cancel_evaluation_run(session, run_id)
    try:
        if run.task_id:
            celery_app.control.revoke(run.task_id, terminate=terminate)
    except (CeleryError, OperationalError, OSError):
        logger.warning("evaluation task revoke failed", exc_info=True)

    updated = await get_evaluation_run(session, run_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    return _run_response(updated)


@router.post(
    "/runs/{run_id}/resume",
    response_model=EvaluationRunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_evaluation_run_endpoint(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EvaluationRunAcceptedResponse:
    """从 checkpoint 恢复 failed/cancelled 评测。"""
    run = await get_evaluation_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    if run.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="evaluation run cannot be resumed")

    task_id = f"evaluation-{run_id}-{uuid4().hex[:8]}"
    resumed = await resume_evaluation_run(session, run_id, task_id=task_id)
    if not resumed:
        raise HTTPException(status_code=409, detail="evaluation run cannot be resumed")
    await session.refresh(run)
    try:
        run_evaluation_task.apply_async(args=[str(run_id)], task_id=task_id)
    except (CeleryError, OperationalError, OSError) as exc:
        await fail_evaluation_run(
            session,
            run_id,
            error_message="evaluation task could not be queued",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="evaluation task could not be queued",
        ) from exc

    return EvaluationRunAcceptedResponse(
        run_id=run_id,
        dataset_name=run.dataset_name,
        task_id=task_id,
        status="queued",
        attempt=run.attempt,
        progress_completed=run.progress_completed,
        progress_total=run.progress_total,
    )


def _run_response(run: EvaluationRun) -> EvalRunResponse:
    return EvalRunResponse.model_validate(
        {
            "run_id": run.id,
            "dataset_name": run.dataset_name,
            "task_id": run.task_id,
            "status": run.status,
            "attempt": run.attempt,
            "progress_completed": run.progress_completed,
            "progress_total": run.progress_total,
            "error_message": run.error_message,
            "created_at": run.created_at.isoformat(),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "results": run.results,
        }
    )
