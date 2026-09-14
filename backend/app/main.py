from fastapi import FastAPI

from app.api.v1 import router as api_v1_router
from app.api.v1.chat import router as chat_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.include_router(api_v1_router, prefix="/api/v1")
    application.include_router(chat_router, prefix="/api")

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    return application


app = create_app()
