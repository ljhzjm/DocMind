from pydantic import BaseModel, Field


class SessionLoginRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)


class SessionResponse(BaseModel):
    authenticated: bool
    auth_required: bool
