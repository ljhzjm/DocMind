from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from app.api.v1 import chat as chat_api
from app.api.v1.chat import get_rag_pipeline
from app.db.session import get_async_session
from app.main import app
from app.models.conversation import Conversation
from app.models.enums import MessageRole
from app.rag.types import AnswerDeltaEvent, DoneEvent, RetrievalEvent
from fastapi.testclient import TestClient


class FakePipeline:
    async def stream(
        self,
        session: object,
        query: str,
        *,
        top_k: int | None = None,
        trace_id: str | None = None,
    ) -> AsyncIterator[RetrievalEvent | AnswerDeltaEvent | DoneEvent]:
        del session, query, top_k, trace_id
        yield RetrievalEvent(latency_ms=12.5, chunk_count=2)
        yield AnswerDeltaEvent(delta="answer ")
        yield AnswerDeltaEvent(delta="[1]")
        yield DoneEvent(citations=[1])


async def override_session() -> AsyncIterator[object]:
    yield object()


def test_chat_stream_emits_retrieval_then_answer_and_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation = Conversation(id=uuid4(), title="question")

    async def fake_create(
        session: object,
        *,
        title: str,
    ) -> Conversation:
        del session, title
        return conversation

    async def fake_get(
        session: object,
        conversation_id: UUID,
    ) -> Conversation | None:
        del session
        return conversation if conversation_id == conversation.id else None

    async def fake_add_message(
        session: object,
        *,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
        citations: list[dict[str, object]] | None = None,
    ) -> None:
        del session, conversation_id, role, content, citations

    monkeypatch.setattr(chat_api, "create_conversation", fake_create)
    monkeypatch.setattr(chat_api, "get_conversation", fake_get)
    monkeypatch.setattr(chat_api, "add_message", fake_add_message)
    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_rag_pipeline] = lambda: FakePipeline()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat/stream", json={"query": "question"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-conversation-id"] == str(conversation.id)
    body = response.text
    assert body.index("event: retrieval") < body.index("event: answer")
    assert body.index("event: answer") < body.index("event: done")
    assert '"chunk_count": 2' in body
    assert '"citations": [1]' in body
