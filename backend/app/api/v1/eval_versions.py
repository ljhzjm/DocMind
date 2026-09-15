from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.eval_dataset_version import EvalDatasetVersion
from app.repositories.eval import list_eval_cases
from app.repositories.eval_versions import (
    ensure_dataset_version,
    list_dataset_versions,
)
from app.schemas.evaluation import EvalDatasetVersionResponse

router = APIRouter(prefix="/eval", tags=["evaluation"])


@router.get(
    "/datasets/{dataset_name}/versions",
    response_model=list[EvalDatasetVersionResponse],
)
async def get_dataset_versions(
    dataset_name: str,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[EvalDatasetVersionResponse]:
    versions = await list_dataset_versions(session, dataset_name)
    return [_version_response(version) for version in versions]


@router.post(
    "/datasets/{dataset_name}/versions",
    response_model=EvalDatasetVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def freeze_dataset_version(
    dataset_name: str,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EvalDatasetVersionResponse:
    stored_cases = await list_eval_cases(session, dataset_name)
    if not stored_cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evaluation dataset not found",
        )
    version = await ensure_dataset_version(
        session,
        dataset_name=dataset_name,
        created_by="manual-freeze",
    )
    return _version_response(version)


def _version_response(version: EvalDatasetVersion) -> EvalDatasetVersionResponse:
    return EvalDatasetVersionResponse(
        id=version.id,
        dataset_name=version.dataset_name,
        revision=version.revision,
        content_hash=version.content_hash,
        case_count=version.case_count,
        created_by=version.created_by,
        created_at=version.created_at.isoformat(),
    )
