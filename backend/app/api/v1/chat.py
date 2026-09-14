import json
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.rag.pipeline import RAGPipeline
from app.rag.types import (
    AnswerDeltaEvent,
    DoneEvent,
    ErrorEvent,
    RetrievalEvent,
)
from app.schemas.chat import ChatStreamRequest

router = APIRouter(prefix="/chat", tags=["chat"])


@lru_cache
def get_rag_pipeline() -> RAGPipeline:
    return RAGPipeline()


@router.post("/stream")
async def stream_chat(
    request: ChatStreamRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    pipeline: Annotated[RAGPipeline, Depends(get_rag_pipeline)],
) -> StreamingResponse:
    """通过 SSE 发送检索元数据、answer 增量和最终引用。"""

    async def event_stream() -> AsyncIterator[str]:
        async for event in pipeline.stream(
            session,
            request.query,
            top_k=request.top_k,
        ):
            if isinstance(event, RetrievalEvent):
                yield _sse(
                    "retrieval",
                    {
                        "latency_ms": event.latency_ms,
                        "chunk_count": event.chunk_count,
                    },
                )
            elif isinstance(event, AnswerDeltaEvent):
                yield _sse("answer", {"delta": event.delta})
            elif isinstance(event, DoneEvent):
                yield _sse("done", {"citations": event.citations})
            elif isinstance(event, ErrorEvent):
                yield _sse("error", {"message": event.message})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, payload: dict[str, object]) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"
