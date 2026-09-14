from fastapi import FastAPI

from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    return application


app = create_app()
