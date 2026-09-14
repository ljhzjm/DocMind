from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MessageRole


class ConversationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ConversationResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: UUID
    role: MessageRole
    content: str
    citations: list[dict[str, object]] | None
    created_at: datetime
