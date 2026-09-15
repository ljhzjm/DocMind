from collections.abc import Sequence

import pytest
from app.core.redis import close_redis
from app.db.session import get_async_engine, get_async_session_factory
from app.evaluation.executor import execute_evaluation_run
from app.evaluation.runner import EvaluationRunner, ProgressCallback
from app.evaluation.types import (
    CaseMetrics,
    ConfigMetrics,
    EvalCase,
    EvaluationCheckpoint,
    EvaluationProgress,
    RetrievalConfig,
)
from app.main import app
from app.models.eval_dataset import EvalDatasetItem
from app.models.evaluation_run import EvaluationRun
from app.workers.celery_app import celery_app
from app.workers.tasks import run_evaluation_task
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


class StaticEvaluationRunner(EvaluationRunner):
    def __init__(self) -> None:
        pass

    async def run(
        self,
        session: AsyncSession,
        *,
        cases: Sequence[EvalCase],
        configs: Sequence[RetrievalConfig],
        progress_callback: ProgressCallback | None = None,
        checkpoint: Sequence[EvaluationCheckpoint] = (),
    ) -> list[ConfigMetrics]:
        del session, checkpoint
        total = len(cases) * len(configs)
        case_metrics = CaseMetrics(
            question=cases[0].question,
            recall_at_5=1.0,
            reciprocal_rank=1.0,
            faithfulness=5.0,
            answer_relevance=5.0,
            ragas_faithfulness=1.0,
            ragas_answer_relevance=1.0,
            latency_ms=10.0,
            first_token_latency_ms=5.0,
            input_tokens=10,
            output_tokens=5,
            estimated_cost=0.001,
            refused=False,
        )
        if progress_callback is not None:
            await progress_callback(
                EvaluationProgress(
                    completed=total,
                    total=total,
                    config_index=0,
                    case_index=0,
                    metrics=case_metrics,
                )
            )
        config = configs[0]
        return [
            ConfigMetrics(
                config=config,
                case_count=len(cases),
                recall_at_5=1.0,
                mrr=1.0,
                faithfulness=5.0,
                answer_relevance=5.0,
                ragas_faithfulness=1.0,
                ragas_answer_relevance=1.0,
                average_latency_ms=10.0,
                average_first_token_latency_ms=5.0,
                average_input_tokens=10.0,
                average_output_tokens=5.0,
                average_estimated_cost=0.001,
                refusal_rate=0.0,
                hallucination_risk=0.0,
                cases=[case_metrics],
            )
        ]


@pytest.mark.asyncio
async def test_run_endpoint_queues_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued: list[tuple[tuple[object, ...], dict[str, object]]] = []
    revoked: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        run_evaluation_task,
        "apply_async",
        lambda *args, **kwargs: queued.append((args, kwargs)),
    )
    monkeypatch.setattr(
        celery_app.control,
        "revoke",
        lambda task_id, terminate: revoked.append((task_id, terminate)),
    )
    dataset_name = "async-api-test"
    try:
        await _cleanup_dataset(dataset_name)
        async with get_async_session_factory()() as session:
            session.add(
                EvalDatasetItem(
                    dataset_name=dataset_name,
                    question="测试问题",
                    reference_answer="测试答案",
                    expected_chunk_ids=[],
                    tags=[],
                    created_by="test",
                )
            )
            await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/eval/run",
                json={
                    "dataset_name": dataset_name,
                    "configs": [
                        {
                            "name": "vector",
                            "mode": "vector",
                            "top_k": 5,
                            "rerank": False,
                        }
                    ],
                },
            )

            assert response.status_code == 202
            payload = response.json()
            assert payload["status"] == "queued"
            assert payload["attempt"] == 0
            assert payload["progress_total"] == 1
            assert queued

            run_id = payload["run_id"]
            cancelled = await client.post(f"/api/v1/eval/runs/{run_id}/cancel")
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"
            assert revoked == [(payload["task_id"], False)]

            resumed = await client.post(f"/api/v1/eval/runs/{run_id}/resume")
            assert resumed.status_code == 202
            assert resumed.json()["status"] == "queued"
            assert resumed.json()["attempt"] == 1
            assert len(queued) == 2
    finally:
        await _cleanup_dataset(dataset_name)
        await close_redis()
        await get_async_engine().dispose()


@pytest.mark.asyncio
async def test_executor_persists_progress_results_and_completion() -> None:
    dataset_name = "async-executor-test"
    try:
        async with get_async_session_factory()() as session:
            session.add(
                EvalDatasetItem(
                    dataset_name=dataset_name,
                    question="执行器问题",
                    reference_answer="执行器答案",
                    expected_chunk_ids=[],
                    tags=[],
                    created_by="test",
                )
            )
            run = EvaluationRun(
                dataset_name=dataset_name,
                task_id="test-task",
                status="queued",
                progress_completed=0,
                progress_total=1,
                configs=[
                    {
                        "name": "vector",
                        "mode": "vector",
                        "top_k": 5,
                        "rerank": False,
                    }
                ],
                results=[],
            )
            session.add(run)
            await session.commit()
            run_id = run.id

        await execute_evaluation_run(run_id, runner=StaticEvaluationRunner())
        async with get_async_session_factory()() as session:
            stored = await session.get(EvaluationRun, run_id)
            assert stored is not None
            assert stored.status == "completed"
            assert stored.progress_completed == 1
            assert stored.progress_total == 1
            assert stored.results[0]["name"] == "vector"
    finally:
        await _cleanup_dataset(dataset_name)
        await get_async_engine().dispose()


async def _cleanup_dataset(dataset_name: str) -> None:
    async with get_async_session_factory()() as session:
        await session.execute(
            delete(EvaluationRun).where(EvaluationRun.dataset_name == dataset_name)
        )
        await session.execute(
            delete(EvalDatasetItem).where(EvalDatasetItem.dataset_name == dataset_name)
        )
        await session.commit()
