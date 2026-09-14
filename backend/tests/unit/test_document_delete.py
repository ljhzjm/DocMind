from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from app.api.v1 import documents as documents_api
from app.db.session import get_async_session
from app.main import app
from app.models.chunk_term import ChunkTerm
from app.models.document import Chunk, Document
from app.models.enums import DocumentStatus
from app.repositories.documents import delete_document
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


def test_delete_document_removes_record_and_uploaded_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    document_id = uuid4()
    source_path = tmp_path / f"{document_id}.md"
    source_path.write_text("content", encoding="utf-8")
    document = Document(
        id=document_id,
        filename="policy.md",
        status=DocumentStatus.READY,
        file_type="md",
        file_size=7,
        chunk_count=1,
    )
    deleted: list[Document] = []

    async def fake_get_document(_session: object, _document_id: object) -> Document:
        return document

    async def fake_delete_document(_session: object, value: Document) -> None:
        deleted.append(value)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, SimpleNamespace())

    monkeypatch.setattr(documents_api, "get_document", fake_get_document)
    monkeypatch.setattr(documents_api, "delete_document", fake_delete_document)
    monkeypatch.setattr(
        documents_api,
        "get_settings",
        lambda: SimpleNamespace(upload_dir=tmp_path),
    )
    app.dependency_overrides[get_async_session] = override_session
    try:
        response = TestClient(app).delete(f"/api/v1/documents/{document_id}")
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 204
    assert deleted == [document]
    assert not source_path.exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_document_cascades_chunks_and_bm25_terms() -> None:
    from app.db.session import get_async_session_factory

    async with get_async_session_factory()() as session:
        document = Document(
            filename="delete-test.md",
            status=DocumentStatus.READY,
            file_type="md",
            file_size=10,
            chunk_count=1,
        )
        session.add(document)
        await session.flush()

        chunk = Chunk(
            document_id=document.id,
            content="待删除的测试切片",
            chunk_index=0,
            page_number=1,
            heading_path=[],
            is_parent=False,
        )
        session.add(chunk)
        await session.flush()
        session.add(
            ChunkTerm(
                term="测试",
                chunk_id=chunk.id,
                term_frequency=1,
            )
        )
        await session.commit()
        document_id = document.id
        chunk_id = chunk.id

    async with get_async_session_factory()() as session:
        stored_document = await session.get(Document, document_id)
        assert stored_document is not None
        await delete_document(session, stored_document)
        assert await session.get(Document, document_id) is None
        assert await session.get(Chunk, chunk_id) is None
        assert (
            await session.get(
                ChunkTerm,
                {"term": "测试", "chunk_id": chunk_id},
            )
            is None
        )
