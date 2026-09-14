import json
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.enums import MessageRole
from app.rag.pipeline import RAGPipeline
from app.rag.types import (
    AnswerDeltaEvent,
    DoneEvent,
    ErrorEvent,
    RetrievalEvent,
)
from app.repositories.conversations import (
    add_message,
    create_conversation,
    get_conversation,
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

    conversation = (
        await get_conversation(session, request.conversation_id)
        if request.conversation_id is not None
        else await create_conversation(session, title=request.query)
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    await add_message(
        session,
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=request.query,
    )

    trace_id = uuid4().hex

    answer_text = ""
    answer_citations: list[int] = []
    answer_contexts: list[dict[str, object]] = []

    async def event_stream() -> AsyncIterator[str]:
        nonlocal answer_text, answer_citations, answer_contexts
        async for event in pipeline.stream(
            session,
            request.query,
            top_k=request.top_k,
            trace_id=trace_id,
        ):
            if isinstance(event, RetrievalEvent):
                answer_contexts = [
                    {
                        "citation_number": context.citation_number,
                        "chunk_id": str(context.hit.chunk_id),
                        "document_name": context.hit.document_name,
                        "page_number": context.hit.page_number,
                    }
                    for context in event.contexts
                ]
                yield _sse(
                    "retrieval",
                    {
                        "latency_ms": event.latency_ms,
                        "chunk_count": event.chunk_count,
                        "trace_id": trace_id,
                        "conversation_id": str(conversation.id),
                        "cached": event.cached,
                        "contexts": [
                            {
                                "citation_number": context.citation_number,
                                "chunk_id": str(context.hit.chunk_id),
                                "content": context.hit.content,
                                "document_name": context.hit.document_name,
                                "page_number": context.hit.page_number,
                                "heading_path": list(context.hit.heading_path),
                                "score": context.hit.score,
                            }
                            for context in event.contexts
                        ],
                    },
                )
            elif isinstance(event, AnswerDeltaEvent):
                answer_text += event.delta
                yield _sse("answer", {"delta": event.delta})
            elif isinstance(event, DoneEvent):
                answer_citations = event.citations
                await add_message(
                    session,
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content=answer_text,
                    citations=answer_contexts,
                )
                yield _sse(
                    "done",
                    {
                        "citations": event.citations,
                        "trace_id": trace_id,
                        "usage": event.usage.model_dump(),
                        "model": event.model_name,
                    },
                )
            elif isinstance(event, ErrorEvent):
                yield _sse(
                    "error",
                    {"message": event.message, "trace_id": trace_id},
                )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Trace-ID": trace_id,
            "X-Conversation-ID": str(conversation.id),
        },
    )


def _sse(event: str, payload: dict[str, object]) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"
