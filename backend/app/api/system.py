import os

from fastapi import APIRouter

from app.core.config import get_settings
from app.llm import load_llm_config
from app.schemas.system import HealthResponse, ModelGatewayStatus

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def api_health() -> HealthResponse:
    """返回服务和模型网关配置状态。"""
    settings = get_settings()
    config = load_llm_config(settings.llm_config_path or None)
    generation_alias = config.routes["final_generation"]
    embedding_alias = config.routes["embedding"]
    generation = config.models[generation_alias]
    embedding = config.models[embedding_alias]
    generation_provider = config.providers[generation.provider]
    embedding_provider = config.providers[embedding.provider]
    configured = bool(
        os.getenv(generation_provider.api_key_env) and os.getenv(embedding_provider.api_key_env)
    )
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        model_gateway=ModelGatewayStatus(
            configured=configured,
            generation_model=generation.model,
            embedding_model=embedding.model,
        ),
    )
