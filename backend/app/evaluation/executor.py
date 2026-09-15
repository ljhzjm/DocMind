import logging
from uuid import UUID

from app.db.session import get_async_session_factory
from app.evaluation.runner import EvaluationRunner
from app.evaluation.serialization import config_metrics_payload
from app.evaluation.types import EvalCase, RetrievalConfig
from app.repositories.eval import list_eval_cases
from app.repositories.evaluation_runs import (
    complete_evaluation_run,
    fail_evaluation_run,
    get_evaluation_run,
    mark_evaluation_run_running,
    update_evaluation_run_progress,
)
from app.retrieval.types import SearchMode

logger = logging.getLogger(__name__)


async def execute_evaluation_run(
    run_id: UUID,
    *,
    runner: EvaluationRunner | None = None,
) -> None:
    """在 Worker 进程执行评测，并把状态、进度和结果写回数据库。"""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        run = await get_evaluation_run(session, run_id)
        if run is None:
            logger.warning("evaluation run not found", extra={"run_id": str(run_id)})
            return
        if run.status == "completed":
            return

        stored_cases = await list_eval_cases(session, run.dataset_name)
        cases = [
            EvalCase(
                id=case.id,
                question=case.question,
                reference_answer=case.reference_answer,
                expected_chunk_ids=tuple(case.expected_chunk_ids),
                tags=tuple(case.tags),
            )
            for case in stored_cases
        ]
        configs = [
            RetrievalConfig(
                name=config["name"],
                mode=SearchMode(config["mode"]),
                top_k=int(config["top_k"]),
                rerank=bool(config["rerank"]),
            )
            for config in run.configs
        ]
        if not cases:
            await fail_evaluation_run(
                session,
                run_id,
                error_message="evaluation dataset is empty",
            )
            return
        await mark_evaluation_run_running(session, run_id)

    async def report_progress(completed: int, total: int) -> None:
        async with session_factory() as progress_session:
            await update_evaluation_run_progress(
                progress_session,
                run_id,
                completed=completed,
                total=total,
            )

    try:
        active_runner = runner or EvaluationRunner()
        async with session_factory() as runner_session:
            results = await active_runner.run(
                runner_session,
                cases=cases,
                configs=configs,
                progress_callback=report_progress,
            )
        async with session_factory() as completion_session:
            await complete_evaluation_run(
                completion_session,
                run_id,
                results=[config_metrics_payload(result) for result in results],
            )
    except Exception as exc:
        logger.exception("evaluation run failed", extra={"run_id": str(run_id)})
        async with session_factory() as failure_session:
            await fail_evaluation_run(
                failure_session,
                run_id,
                error_message=str(exc),
            )
        raise
