from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence

import httpx

from app.llm.base import (
    ChatResult,
    EmbeddingResult,
    FinishEvent,
    LLMMessage,
    LLMProvider,
    LLMResponseError,
    LLMStreamEvent,
    TextDeltaEvent,
    TokenUsage,
    UsageEvent,
)
from app.llm.cost import (
    CallCostRecord,
    CallTimer,
    CostRecorder,
    LoggingCostRecorder,
    resolve_request_id,
    usage_from_counts,
)
from app.llm.openai_schemas import (
    ChatPayload,
    ChoicePayload,
    parse_chat_chunk,
    parse_chat_response,
    parse_embedding_response,
)
from app.llm.openai_transport import (
    OpenAITransport,
    Sleep,
    response_request_id,
)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        stream_include_usage: bool = False,
        response_format_json: bool = False,
        default_headers: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        recorder: CostRecorder | None = None,
        transport: OpenAITransport | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._model = model
        self._stream_include_usage = stream_include_usage
        self._response_format_json = response_format_json
        self._recorder = recorder or LoggingCostRecorder()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **(default_headers or {}),
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._transport = transport or OpenAITransport(
            base_url=base_url,
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            client=client,
            sleep=sleep,
        )

    async def aclose(self) -> None:
        await self._transport.aclose()

    def chat_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        return self._chat_stream(
            messages,
            task=task,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _chat_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> AsyncIterator[LLMStreamEvent]:
        timer = CallTimer()
        usage = usage_from_counts()
        request_id: str | None = None
        finish_reason: str | None = None
        success = False
        try:
            async for sse_payload in self._transport.iter_sse(
                "/chat/completions",
                payload=self._chat_payload(
                    messages,
                    stream=True,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            ):
                request_id = sse_payload.request_id or request_id
                chunk = parse_chat_chunk(sse_payload.data)
                request_id = request_id or chunk.id
                choice = self._first_choice(chunk)
                content = choice.delta.content if choice and choice.delta else None
                if content:
                    yield TextDeltaEvent(text=content, request_id=request_id)
                chunk_usage = chunk.usage.to_usage() if chunk.usage else None
                if chunk_usage is not None:
                    usage = chunk_usage
                    yield UsageEvent(usage=chunk_usage, request_id=request_id)
                if choice and choice.finish_reason is not None:
                    finish_reason = choice.finish_reason
                    yield FinishEvent(
                        finish_reason=choice.finish_reason,
                        usage=chunk_usage,
                        request_id=request_id,
                    )
            success = True
        finally:
            self._record(
                request_id=request_id,
                task=task,
                usage=usage,
                timer=timer,
                finish_reason=finish_reason,
                success=success,
            )

    async def chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        task: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        timer = CallTimer()
        usage = usage_from_counts()
        request_id: str | None = None
        finish_reason: str | None = None
        success = False
        try:
            response = await self._transport.request(
                "POST",
                "/chat/completions",
                payload=self._chat_payload(
                    messages,
                    stream=False,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            )
            request_id = response_request_id(response)
            payload = parse_chat_response(response.content)
            request_id = request_id or payload.id
            choice = self._require_choice(payload)
            usage = payload.usage.to_usage() if payload.usage else usage
            finish_reason = choice.finish_reason
            text = choice.message.content if choice.message is not None else ""
            success = True
            return ChatResult(
                text=text or "",
                usage=usage,
                finish_reason=finish_reason,
                request_id=request_id,
            )
        finally:
            self._record(
                request_id=request_id,
                task=task,
                usage=usage,
                timer=timer,
                finish_reason=finish_reason,
                success=success,
            )

    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: str | None = None,
    ) -> EmbeddingResult:
        timer = CallTimer()
        usage = usage_from_counts()
        request_id: str | None = None
        success = False
        try:
            response = await self._transport.request(
                "POST",
                "/embeddings",
                payload={"model": self._model, "input": list(texts)},
            )
            request_id = response_request_id(response)
            payload = parse_embedding_response(response.content)
            usage = payload.usage.to_usage() if payload.usage else usage
            success = True
            return EmbeddingResult(
                embeddings=[item.embedding for item in payload.data],
                usage=usage,
                request_id=request_id,
            )
        finally:
            self._record(
                request_id=request_id,
                task=task,
                usage=usage,
                timer=timer,
                finish_reason=None,
                success=success,
            )

    def _chat_payload(
        self,
        messages: Sequence[LLMMessage],
        *,
        stream: bool,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [message.model_dump() for message in messages],
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if self._response_format_json:
            payload["response_format"] = {"type": "json_object"}
        if stream and self._stream_include_usage:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _record(
        self,
        *,
        request_id: str | None,
        task: str | None,
        usage: TokenUsage,
        timer: CallTimer,
        finish_reason: str | None,
        success: bool,
    ) -> None:
        self._recorder.record(
            CallCostRecord(
                request_id=resolve_request_id(request_id),
                provider=self._provider_name,
                model=self._model,
                task=task,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                duration_ms=timer.elapsed_ms,
                finish_reason=finish_reason,
                success=success,
            )
        )

    @staticmethod
    def _first_choice(payload: ChatPayload) -> ChoicePayload | None:
        if not payload.choices:
            return None
        return payload.choices[0]

    @staticmethod
    def _require_choice(payload: ChatPayload) -> ChoicePayload:
        choice = OpenAICompatibleProvider._first_choice(payload)
        if choice is None:
            raise LLMResponseError("chat response did not contain choices")
        return choice
