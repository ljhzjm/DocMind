from pydantic import BaseModel


class ModelGatewayStatus(BaseModel):
    configured: bool
    generation_model: str
    embedding_model: str


class HealthResponse(BaseModel):
    status: str
    service: str
    model_gateway: ModelGatewayStatus
