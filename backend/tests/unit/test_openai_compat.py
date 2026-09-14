from collections.abc import Callable, Coroutine

import httpx
import pytest
from app.llm.base import (
    FinishEvent,
    LLMMessage,
    TextDeltaEvent,
    UsageEvent,
)
from app.llm.config import load_llm_config
from app.llm.cost import CallCostRecord
from app.llm.openai_compat import OpenAICompatibleProvider

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


class RecordingCostRecorder:
    def __init__(self) -> None:
        self.records: list[CallCostRecord] = []

    def record(self, record: CallCostRecord) -> None:
        self.records.append(record)


def build_provider(
    handler: Handler,
    *,
    recorder: RecordingCostRecorder | None = None,
    sleep: Callable[[float], Coroutine[None, None, None]] | None = None,
) -> tuple[OpenAICompatibleProvider, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        provider_name="test-provider",
        base_url="https://llm.example/v1",
        api_key="test-key",
        model="test-model",
        max_retries=2,
        retry_backoff_seconds=0.01,
        stream_include_usage=True,
        client=client,
        recorder=recorder,
        sleep=sleep,
    )
    return provider, client


@pytest.mark.asyncio
async def test_chat_retries_429_and_5xx_then_records_cost() -> None:
    calls = 0
    delays: list[float] = []
    recorder = RecordingCostRecorder()
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        requests.append(request)
        if calls == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        if calls == 2:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(
            200,
            headers={"x-request-id": "req-chat-1"},
            json={
                "id": "chatcmpl-1",
                "choices": [
                    {
                        "message": {"content": "answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 5,
                    "total_tokens": 16,
                },
            },
        )

    async def sleep(delay: float) -> None:
        delays.append(delay)

    provider, client = build_provider(handler, recorder=recorder, sleep=sleep)
    async with client:
        result = await provider.chat(
            [LLMMessage(role="user", content="hello")],
            task="query_rewrite",
        )

    assert calls == 3
    assert delays == [0.01, 0.02]
    assert result.text == "answer"
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 5
    assert result.request_id == "req-chat-1"
    assert requests[0].url.path.endswith("/chat/completions")
    assert b'"model":"test-model"' in requests[0].content
    assert recorder.records[0].model == "test-model"
    assert recorder.records[0].duration_ms >= 0
    assert recorder.records[0].request_id == "req-chat-1"


@pytest.mark.asyncio
async def test_chat_stream_parses_sse_deltas_usage_and_finish() -> None:
    recorder = RecordingCostRecorder()

    async def handler(request: httpx.Request) -> httpx.Response:
        body = "".join(
            [
                'data: {"id":"stream-1","choices":[{"delta":{"content":"Hel"},'
                '"finish_reason":null}]}\n\n',
                'data: {"id":"stream-1","choices":[{"delta":{"content":"lo"},'
                '"finish_reason":"stop"}],"usage":{"prompt_tokens":3,'
                '"completion_tokens":2,"total_tokens":5}}\n\n',
                "data: [DONE]\n\n",
            ]
        )
        return httpx.Response(
            200,
            headers={
                "content-type": "text/event-stream",
                "x-request-id": "req-stream-1",
            },
            content=body.encode(),
        )

    provider, client = build_provider(handler, recorder=recorder)
    async with client:
        events = [
            event
            async for event in provider.chat_stream(
                [LLMMessage(role="user", content="hello")],
                task="final_generation",
            )
        ]

    assert [event.type for event in events] == [
        "text_delta",
        "text_delta",
        "usage",
        "finish",
    ]
    assert isinstance(events[0], TextDeltaEvent)
    assert events[0].text == "Hel"
    assert isinstance(events[2], UsageEvent)
    assert events[2].usage.total_tokens == 5
    assert isinstance(events[3], FinishEvent)
    assert events[3].finish_reason == "stop"
    assert recorder.records[0].request_id == "req-stream-1"
    assert recorder.records[0].input_tokens == 3
    assert recorder.records[0].output_tokens == 2


@pytest.mark.asyncio
async def test_embed_returns_vectors_from_openai_compatible_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-request-id": "req-embed-1"},
            json={
                "data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}],
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )

    provider, client = build_provider(handler)
    async with client:
        result = await provider.embed(["one", "two"], task="embedding")

    assert result.embeddings == [[0.1, 0.2], [0.3, 0.4]]
    assert result.usage.input_tokens == 2
    assert result.request_id == "req-embed-1"


def test_default_config_loads_provider_and_model_aliases() -> None:
    config = load_llm_config()

    assert config.routes["intent_classification"] == "cheap"
    assert config.routes["query_rewrite"] == "cheap"
    assert config.routes["final_generation"] == "strong"
    assert config.models["cheap"].provider == "deepseek"
    assert config.providers["qwen"].base_url.endswith("/compatible-mode/v1")
