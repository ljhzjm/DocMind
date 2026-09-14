from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.api.v1 import router as api_v1_router
from app.api.v1.chat import router as chat_router
from app.core.config import get_settings
from app.core.redis import close_redis
from app.observability.logging import configure_json_logging


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    del application
    yield
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_json_logging(settings.log_level)
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(RequestContextMiddleware)
    application.include_router(api_v1_router, prefix="/api/v1")
    application.include_router(chat_router, prefix="/api")

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    return application


app = create_app()
