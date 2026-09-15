import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.auth import client_ip, resolve_identity
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
    """按认证身份限流，匿名请求按可信代理后的客户端 IP 限流。"""

    def __init__(self, app: object) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limiter = TokenBucketRateLimiter()

    async def dispatch(self, request: Request, call_next: NextCall) -> Response:
        if not request.url.path.startswith("/api") or request.url.path == "/api/health":
            return await call_next(request)

        settings = get_settings()
        identity = getattr(request.state, "auth_identity", None)
        limiter_key = (
            identity.rate_limit_key
            if identity is not None
            else f"ip:{client_ip(request, settings)}"
        )
        decision = await self._limiter.check(limiter_key)
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


class APIKeyMiddleware(BaseHTTPMiddleware):
    """支持 API Key 和浏览器 HttpOnly 会话认证。"""

    async def dispatch(self, request: Request, call_next: NextCall) -> Response:
        settings = get_settings()
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        identity = resolve_identity(request, settings)
        request.state.auth_identity = identity
        if (
            not settings.require_api_key
            or request.url.path == "/api/health"
            or request.url.path.startswith("/api/auth/session")
            or identity is not None
        ):
            return await call_next(request)

        if identity is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or missing API key"},
            )
        return await call_next(request)
