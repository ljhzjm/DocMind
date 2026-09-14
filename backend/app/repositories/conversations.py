from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message
from app.models.enums import MessageRole


async def list_conversations(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[Conversation]:
    result = await session.scalars(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
    )
    return list(result.all())


async def get_conversation(
    session: AsyncSession,
    conversation_id: UUID,
) -> Conversation | None:
    return await session.get(Conversation, conversation_id)


async def create_conversation(
    session: AsyncSession,
    *,
    title: str,
) -> Conversation:
    conversation = Conversation(title=title[:255])
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def list_messages(
    session: AsyncSession,
    conversation_id: UUID,
) -> list[Message]:
    result = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.all())


async def add_message(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    role: MessageRole,
    content: str,
    citations: list[dict[str, object]] | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations=citations,
    )
    session.add(message)
    conversation = await session.get(Conversation, conversation_id)
    if conversation is not None:
        conversation.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(message)
    return message
