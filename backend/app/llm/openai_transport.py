from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Self

import httpx

from app.llm.base import LLMHTTPError, LLMRetryExhausted
from app.llm.openai_sse import SSEData, parse_sse_line

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class SSEPayload:
    data: str
    request_id: str | None


class RetryableResponse(Exception):
    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"retryable HTTP {response.status_code}")
        self.response = response


class OpenAITransport:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        client: httpx.AsyncClient | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._max_retries = max_retries
        self._retry_backoff_seconds: float = retry_backoff_seconds
        self._sleep = sleep or asyncio.sleep
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object],
    ) -> httpx.Response:
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            try:
                response = await self._client.request(
                    method,
                    self._url(path),
                    headers=self._headers,
                    json=payload,
                )
            except httpx.RequestError as exc:
                if attempt == attempts - 1:
                    raise LLMRetryExhausted(attempts) from exc
                await self._sleep(self._retry_delay(exc, attempt))
                continue

            if self._is_retryable(response.status_code):
                if attempt == attempts - 1:
                    raise LLMRetryExhausted(
                        attempts,
                        response_request_id(response),
                    )
                await self._sleep(self._retry_delay(response, attempt))
                continue

            if response.is_error:
                raise LLMHTTPError(
                    response.status_code,
                    response_request_id(response),
                )
            return response

        raise LLMRetryExhausted(attempts)

    async def iter_sse(
        self,
        path: str,
        *,
        payload: dict[str, object],
    ) -> AsyncIterator[SSEPayload]:
        attempts = self._max_retries + 1

        for attempt in range(attempts):
            emitted = False
            try:
                async with self._client.stream(
                    "POST",
                    self._url(path),
                    headers=self._headers,
                    json=payload,
                ) as response:
                    request_id = response_request_id(response)
                    if self._is_retryable(response.status_code):
                        raise RetryableResponse(response)
                    if response.is_error:
                        raise LLMHTTPError(response.status_code, request_id)

                    async for line in response.aiter_lines():
                        parsed = parse_sse_line(line)
                        if parsed is None:
                            continue
                        if parsed.done:
                            return
                        emitted = True
                        yield self._payload(parsed, request_id)
                    return
            except (RetryableResponse, httpx.RequestError) as exc:
                if emitted or attempt == attempts - 1:
                    raise LLMRetryExhausted(attempts) from exc
                await self._sleep(self._retry_delay(exc, attempt))

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    @staticmethod
    def _payload(data: SSEData, request_id: str | None) -> SSEPayload:
        return SSEPayload(data=data.data, request_id=request_id)

    @staticmethod
    def _is_retryable(status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code <= 599

    def _retry_delay(
        self,
        error: RetryableResponse | httpx.Response | httpx.RequestError,
        attempt: int,
    ) -> float:
        response = error.response if isinstance(error, RetryableResponse) else error
        if isinstance(response, httpx.Response):
            retry_after = response.headers.get("retry-after")
            if isinstance(retry_after, str):
                try:
                    return max(0.0, float(retry_after))
                except ValueError:
                    pass
        return float(self._retry_backoff_seconds) * float(2**attempt)


def response_request_id(response: httpx.Response) -> str | None:
    request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
    return str(request_id) if request_id is not None else None
