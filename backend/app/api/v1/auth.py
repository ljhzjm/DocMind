from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.auth import (
    issue_session_token,
    resolve_identity,
    verify_api_key,
)
from app.core.config import get_settings
from app.schemas.auth import SessionLoginRequest, SessionResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/session", response_model=SessionResponse)
async def get_session(request: Request) -> SessionResponse:
    """返回当前浏览器会话状态，供前端路由守卫使用。"""
    settings = get_settings()
    identity = resolve_identity(request, settings)
    return SessionResponse(
        authenticated=not settings.require_api_key or identity is not None,
        auth_required=settings.require_api_key,
    )


@router.post("/session", response_model=SessionResponse)
async def create_session(
    payload: SessionLoginRequest,
    response: Response,
) -> SessionResponse:
    """校验访问密钥并设置 HttpOnly、SameSite=Strict 会话 Cookie。"""
    settings = get_settings()
    if not settings.require_api_key:
        return SessionResponse(authenticated=True, auth_required=False)

    fingerprint = verify_api_key(settings, payload.api_key)
    if fingerprint is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid API key",
        )

    response.set_cookie(
        key=settings.session_cookie_name,
        value=issue_session_token(settings, fingerprint),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.app_env in {"production", "staging"},
        samesite="strict",
        path="/",
    )
    return SessionResponse(authenticated=True, auth_required=True)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(response: Response) -> Response:
    """清除浏览器会话 Cookie。"""
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.app_env in {"production", "staging"},
        samesite="strict",
        path="/",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
