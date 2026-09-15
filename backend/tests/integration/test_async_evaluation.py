from collections.abc import Sequence

import pytest
from app.core.redis import close_redis
from app.db.session import get_async_engine, get_async_session_factory
from app.evaluation.executor import execute_evaluation_run
from app.evaluation.runner import EvaluationRunner, ProgressCallback
from app.evaluation.types import ConfigMetrics, EvalCase, RetrievalConfig
from app.main import app
from app.models.eval_dataset import EvalDatasetItem
from app.models.evaluation_run import EvaluationRun
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
    ) -> list[ConfigMetrics]:
        del session
        total = len(cases) * len(configs)
        if progress_callback is not None:
            await progress_callback(0, total)
            await progress_callback(total, total)
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
                cases=[],
            )
        ]


@pytest.mark.asyncio
async def test_run_endpoint_queues_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        run_evaluation_task,
        "apply_async",
        lambda *args, **kwargs: queued.append((args, kwargs)),
    )
    dataset_name = "async-api-test"
    try:
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
        assert payload["progress_total"] == 1
        assert queued
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
