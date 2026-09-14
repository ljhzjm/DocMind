from uuid import UUID

from app.core.config import get_settings
from app.db.session import get_sync_session_factory
from app.ingestion.service import ingest_document
from app.workers.celery_app import celery_app


@celery_app.task(name="docmind.ingestion.process_document")
def process_document_task(document_id: str) -> int:
    """后台解析文档并返回写入的切片数。"""
    settings = get_settings()
    with get_sync_session_factory()() as session:
        return ingest_document(session, UUID(document_id), settings)
