import pytest
from app import main as app_main
from app.api import middleware
from app.api.v1 import auth as auth_api
from app.core.auth import (
    api_key_fingerprint,
    client_ip,
    issue_session_token,
    verify_api_key,
    verify_session_token,
)
from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request


def _settings(*, require_api_key: bool = True) -> Settings:
    return Settings(
        app_env="test",
        require_api_key=require_api_key,
        api_keys="test-secret-key",
        session_secret_key="session-signing-secret-for-tests-1234567890",
        trust_proxy_headers=True,
    )


def test_session_token_is_signed_and_rejects_tampering() -> None:
    settings = _settings()
    subject = api_key_fingerprint("test-secret-key")

    token = issue_session_token(settings, subject)

    assert verify_session_token(settings, token) == subject
    assert verify_session_token(settings, f"{token}x") is None
    assert verify_session_token(settings, "malformed-token") is None
    assert verify_session_token(settings, "é.zz") is None
    assert verify_api_key(settings, "wrong-key") is None
    assert verify_api_key(settings, "test-secret-key") == subject


def test_auth_requires_api_keys_and_signing_secret() -> None:
    with pytest.raises(ValidationError, match="api_keys"):
        Settings(require_api_key=True, session_secret_key="x" * 32)

    with pytest.raises(ValidationError, match="session_secret_key"):
        Settings(require_api_key=True, api_keys="secret")


def test_client_ip_uses_forwarded_header_only_when_trusted() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"203.0.113.10, 10.0.0.2")],
            "client": ("172.20.0.5", 1234),
        }
    )

    assert client_ip(request, _settings()) == "203.0.113.10"
    assert client_ip(request, Settings(trust_proxy_headers=False)) == "172.20.0.5"


def test_login_cookie_protects_api_and_logout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    monkeypatch.setattr(middleware, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr(
        middleware,
        "TokenBucketRateLimiter",
        lambda: RecordingLimiter(),
    )
    application = create_app()

    with TestClient(application) as client:
        assert client.get("/api/v1/search?q=test").status_code == 401
        login = client.post(
            "/api/auth/session",
            json={"api_key": "test-secret-key"},
        )
        assert login.status_code == 200
        assert "httponly" in login.headers["set-cookie"].lower()
        assert client.get("/api/auth/session").json()["authenticated"] is True
        assert client.delete("/api/auth/session").status_code == 204
        assert client.get("/api/auth/session").json()["authenticated"] is False


class RecordingLimiter:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def check(self, key: str) -> object:
        self.keys.append(key)
        return type("Decision", (), {"allowed": True, "retry_after_seconds": 0})()


def test_rate_limit_identity_ignores_spoofed_session_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(require_api_key=False)
    limiter = RecordingLimiter()
    monkeypatch.setattr(middleware, "get_settings", lambda: settings)
    monkeypatch.setattr(
        middleware,
        "TokenBucketRateLimiter",
        lambda: limiter,
    )
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    application = create_app()

    with TestClient(application) as client:
        client.get("/api/auth/session", headers={"x-session-id": "first"})
        client.get("/api/auth/session", headers={"x-session-id": "second"})

    assert limiter.keys == ["ip:testclient", "ip:testclient"]
