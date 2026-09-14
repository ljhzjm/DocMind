from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from celery.exceptions import CeleryError
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from kombu.exceptions import OperationalError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_async_session
from app.ingestion.uploads import (
    UploadValidationError,
    save_upload_file,
    validate_upload_filename,
)
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.repositories.documents import (
    create_document,
    get_document,
    set_document_status,
)
from app.schemas.document import DocumentStatusResponse, DocumentUploadResponse
from app.workers.tasks import process_document_task

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DocumentUploadResponse:
    """校验上传文件、写入待处理记录，并立即返回 Celery 任务 ID。"""
    settings = get_settings()
    try:
        safe_filename, file_type = validate_upload_filename(
            file.filename,
            allowed_extensions=settings.allowed_extensions,
        )
    except UploadValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    document_id = uuid4()
    destination = settings.upload_dir / f"{document_id}.{file_type}"
    try:
        file_size = await save_upload_file(
            file,
            destination,
            max_size_bytes=settings.max_upload_size_bytes,
        )
    except UploadValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc

    document = Document(
        id=document_id,
        filename=safe_filename,
        status=DocumentStatus.UPLOADED,
        file_type=file_type,
        file_size=file_size,
        chunk_count=0,
    )
    try:
        await create_document(session, document)
    except SQLAlchemyError:
        destination.unlink(missing_ok=True)
        raise

    task_id = str(document_id)

    try:
        process_document_task.apply_async(args=[task_id], task_id=task_id)
    except (CeleryError, OperationalError, OSError) as exc:
        await set_document_status(session, document, DocumentStatus.FAILED)
        Path(destination).unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="document task could not be queued",
        ) from exc

    return DocumentUploadResponse(
        document_id=document_id,
        task_id=task_id,
        status=document.status,
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DocumentStatusResponse:
    """返回文档解析状态和当前切片数量，供前端轮询。"""
    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )
    return DocumentStatusResponse(
        document_id=document.id,
        filename=document.filename,
        status=document.status,
        chunk_count=document.chunk_count,
    )
