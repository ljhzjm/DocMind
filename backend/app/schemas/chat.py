from uuid import UUID

from pydantic import BaseModel, Field


class ChatStreamRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
