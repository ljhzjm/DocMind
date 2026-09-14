from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.repositories.conversations import (
    create_conversation,
    get_conversation,
    list_conversations,
    list_messages,
)
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationResponse,
    MessageResponse,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationResponse])
async def get_conversations(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[ConversationResponse]:
    conversations = await list_conversations(session)
    return [
        ConversationResponse(
            id=item.id,
            title=item.title,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in conversations
    ]


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def new_conversation(
    request: ConversationCreateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ConversationResponse:
    conversation = await create_conversation(session, title=request.title)
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_conversation_messages(
    conversation_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[MessageResponse]:
    conversation = await get_conversation(session, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    messages = await list_messages(session, conversation_id)
    return [
        MessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            citations=message.citations,
            created_at=message.created_at,
        )
        for message in messages
    ]
