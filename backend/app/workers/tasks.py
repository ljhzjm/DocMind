import asyncio
from uuid import UUID

from app.core.config import get_settings
from app.db.session import get_async_session_factory, get_sync_session_factory
from app.ingestion.embedding_backfill import backfill_document_embeddings
from app.ingestion.service import ingest_document
from app.workers.celery_app import celery_app


@celery_app.task(name="docmind.ingestion.process_document")
def process_document_task(document_id: str) -> int:
    """后台解析文档并返回写入的切片数。"""
    settings = get_settings()
    with get_sync_session_factory()() as session:
        return ingest_document(session, UUID(document_id), settings)


@celery_app.task(name="docmind.ingestion.backfill_embeddings")
def backfill_document_embeddings_task(document_id: str) -> int:
    """为历史文档异步补齐向量。"""

    async def run() -> int:
        async with get_async_session_factory()() as session:
            return await backfill_document_embeddings(session, UUID(document_id))

    return asyncio.run(run())
