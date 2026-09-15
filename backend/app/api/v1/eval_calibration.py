from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_async_session
from app.evaluation.calibration import calibrate_refusal_threshold
from app.evaluation.types import EvalCase, RetrievalConfig
from app.models.retrieval_threshold import RetrievalThreshold
from app.rag.refusal import rerank_provider_key
from app.rag.rerank import create_reranker
from app.repositories.eval import list_eval_cases
from app.repositories.retrieval_thresholds import (
    list_retrieval_thresholds,
    upsert_retrieval_threshold,
)
from app.schemas.evaluation import (
    RefusalThresholdCalibrationRequest,
    RefusalThresholdResponse,
)

router = APIRouter(prefix="/eval/thresholds", tags=["evaluation"])


@router.get("", response_model=list[RefusalThresholdResponse])
async def get_retrieval_thresholds(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[RefusalThresholdResponse]:
    records = await list_retrieval_thresholds(session)
    return [_threshold_response(record) for record in records]


@router.post(
    "/calibrate",
    response_model=RefusalThresholdResponse,
    status_code=status.HTTP_201_CREATED,
)
async def calibrate_threshold(
    request: RefusalThresholdCalibrationRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> RefusalThresholdResponse:
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
    config = RetrievalConfig(
        name=request.config.name,
        mode=request.config.mode,
        top_k=request.config.top_k,
        rerank=request.config.rerank,
    )
    settings = get_settings()
    calibration = await calibrate_refusal_threshold(
        session,
        cases=cases,
        config=config,
        reranker=create_reranker(settings) if config.rerank else None,
    )
    provider_key = rerank_provider_key(settings, rerank_enabled=config.rerank)
    record = await upsert_retrieval_threshold(
        session,
        mode=config.mode.value,
        top_k=config.top_k,
        rerank_provider=provider_key,
        threshold=calibration.threshold,
        sample_count=calibration.sample_count,
        metrics=calibration.metrics(),
    )
    return _threshold_response(record)


def _threshold_response(record: RetrievalThreshold) -> RefusalThresholdResponse:
    return RefusalThresholdResponse(
        mode=record.mode,
        top_k=record.top_k,
        rerank_provider=record.rerank_provider,
        threshold=record.threshold,
        sample_count=record.sample_count,
        metrics=record.metrics,
        created_at=record.created_at.isoformat(),
    )
