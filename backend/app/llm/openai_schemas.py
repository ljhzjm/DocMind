from pydantic import BaseModel, ConfigDict, ValidationError

from app.llm.base import LLMResponseError, TokenUsage


class UsagePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_usage(self) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.prompt_tokens,
            output_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
        )


class DeltaPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str | None = None


class MessagePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str | None = None


class ChoicePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    delta: DeltaPayload | None = None
    message: MessagePayload | None = None
    finish_reason: str | None = None


class ChatPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    choices: list[ChoicePayload] = []
    usage: UsagePayload | None = None


class EmbeddingItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    embedding: list[float]


class EmbeddingPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: list[EmbeddingItem]
    usage: UsagePayload | None = None


def parse_chat_response(content: bytes) -> ChatPayload:
    try:
        return ChatPayload.model_validate_json(content)
    except ValidationError as exc:
        raise LLMResponseError("invalid chat response") from exc


def parse_embedding_response(content: bytes) -> EmbeddingPayload:
    try:
        return EmbeddingPayload.model_validate_json(content)
    except ValidationError as exc:
        raise LLMResponseError("invalid embedding response") from exc


def parse_chat_chunk(data: str) -> ChatPayload:
    try:
        return ChatPayload.model_validate_json(data)
    except ValidationError as exc:
        raise LLMResponseError("invalid SSE payload") from exc
