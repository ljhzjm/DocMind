import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.rate_limit import TokenBucketRateLimiter
from app.observability.context import request_id_context, trace_id_context

logger = logging.getLogger(__name__)
NextCall = Callable[[Request], Awaitable[Response]]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """注入 request_id，并输出包含状态码和耗时的 JSON 访问日志。"""

    async def dispatch(self, request: Request, call_next: NextCall) -> Response:
        request_id = request.headers.get("x-request-id") or uuid4().hex
        token = request_id_context.set(request_id)
        started_at = perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            return response
        finally:
            request_id_context.reset(token)
            trace_id_context.set(None)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """对 /api 请求执行 IP + 会话组合令牌桶限流。"""

    def __init__(self, app: object) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limiter = TokenBucketRateLimiter()

    async def dispatch(self, request: Request, call_next: NextCall) -> Response:
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        settings = get_settings()
        client_ip = request.client.host if request.client else "unknown"
        session_id = request.headers.get("x-session-id", "anonymous")
        decision = await self._limiter.check(f"{client_ip}:{session_id}")
        if not decision.allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded"},
                headers={
                    "Retry-After": str(max(1, decision.retry_after_seconds)),
                    "X-RateLimit-Limit": str(settings.rate_limit_capacity),
                },
            )
        return await call_next(request)
