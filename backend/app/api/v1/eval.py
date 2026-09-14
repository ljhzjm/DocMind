from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.evaluation.runner import EvaluationRunner
from app.evaluation.types import ConfigMetrics, EvalCase, RetrievalConfig
from app.models.eval_dataset import EvalDatasetItem
from app.repositories.eval import (
    create_eval_case,
    list_eval_cases,
    list_eval_dataset_summaries,
)
from app.schemas.evaluation import (
    CaseMetricsResponse,
    ConfigMetricsResponse,
    EvalCaseCreateRequest,
    EvalCaseResponse,
    EvalDatasetSummary,
    EvalRunRequest,
    EvalRunResponse,
)

router = APIRouter(prefix="/eval", tags=["evaluation"])


@lru_cache
def get_evaluation_runner() -> EvaluationRunner:
    return EvaluationRunner()


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


@router.post("/run", response_model=EvalRunResponse)
async def run_evaluation(
    request: EvalRunRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    runner: Annotated[EvaluationRunner, Depends(get_evaluation_runner)],
) -> EvalRunResponse:
    stored_cases = await list_eval_cases(session, request.dataset_name)
    if not stored_cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evaluation dataset not found",
        )

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
            name=config.name,
            mode=config.mode,
            top_k=config.top_k,
            rerank=config.rerank,
        )
        for config in request.configs
    ]
    results = await runner.run(session, cases=cases, configs=configs)
    return EvalRunResponse(
        dataset_name=request.dataset_name,
        results=[_config_response(result) for result in results],
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


def _config_response(result: ConfigMetrics) -> ConfigMetricsResponse:
    return ConfigMetricsResponse(
        name=result.config.name,
        mode=result.config.mode,
        top_k=result.config.top_k,
        rerank=result.config.rerank,
        case_count=result.case_count,
        recall_at_5=result.recall_at_5,
        mrr=result.mrr,
        faithfulness=result.faithfulness,
        answer_relevance=result.answer_relevance,
        ragas_faithfulness=result.ragas_faithfulness,
        ragas_answer_relevance=result.ragas_answer_relevance,
        average_latency_ms=result.average_latency_ms,
        average_estimated_cost=result.average_estimated_cost,
        cases=[
            CaseMetricsResponse(
                question=case.question,
                recall_at_5=case.recall_at_5,
                reciprocal_rank=case.reciprocal_rank,
                faithfulness=case.faithfulness,
                answer_relevance=case.answer_relevance,
                ragas_faithfulness=case.ragas_faithfulness,
                ragas_answer_relevance=case.ragas_answer_relevance,
                latency_ms=case.latency_ms,
                estimated_cost=case.estimated_cost,
                error=case.error,
            )
            for case in result.cases
        ],
    )
