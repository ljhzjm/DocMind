from collections.abc import AsyncIterator

from app.api.v1.chat import get_rag_pipeline
from app.db.session import get_async_session
from app.main import app
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


def test_chat_stream_emits_retrieval_then_answer_and_done() -> None:
    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_rag_pipeline] = lambda: FakePipeline()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat/stream", json={"query": "question"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert body.index("event: retrieval") < body.index("event: answer")
    assert body.index("event: answer") < body.index("event: done")
    assert '"chunk_count": 2' in body
    assert '"citations": [1]' in body
