from pathlib import Path
from uuid import UUID

import pymupdf
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ingestion.chunking import StructureAwareChunker
from app.ingestion.parsers import UnsupportedDocumentTypeError, parse_document
from app.models.enums import DocumentStatus
from app.repositories.documents import (
    get_document_sync,
    replace_chunks,
    set_document_status_sync,
)


class DocumentNotFoundError(LookupError):
    """后台任务引用的文档不存在。"""


class DocumentIngestionError(RuntimeError):
    """文档解析、切片或入库失败。"""


def ingest_document(
    session: Session,
    document_id: UUID,
    settings: Settings,
) -> int:
    """解析文件、结构切片并原子替换 chunks，最终更新文档状态。"""
    document = get_document_sync(session, document_id)
    if document is None:
        raise DocumentNotFoundError(str(document_id))

    set_document_status_sync(session, document, DocumentStatus.PARSING)
    source_path = settings.upload_dir / f"{document.id}.{document.file_type}"

    try:
        blocks = parse_document(Path(source_path))
        drafts = StructureAwareChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        ).split(blocks)
        replace_chunks(session, document, drafts)
        document.status = DocumentStatus.READY
        session.commit()
        return len(drafts)
    except (
        OSError,
        UnicodeDecodeError,
        UnsupportedDocumentTypeError,
        pymupdf.FileDataError,
        ValueError,
        SQLAlchemyError,
    ) as exc:
        session.rollback()
        failed_document = get_document_sync(session, document_id)
        if failed_document is not None:
            set_document_status_sync(
                session,
                failed_document,
                DocumentStatus.FAILED,
            )
        raise DocumentIngestionError(str(document_id)) from exc
