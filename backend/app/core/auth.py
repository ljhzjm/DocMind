import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from app.core.config import Settings

AuthMethod = Literal["api_key", "session"]


@dataclass(frozen=True)
class AuthIdentity:
    subject: str
    method: AuthMethod

    @property
    def rate_limit_key(self) -> str:
        return f"{self.method}:{self.subject}"


def api_key_fingerprint(api_key: str) -> str:
    """返回 API Key 的稳定指纹，永远不把原始密钥写入 Cookie 或日志。"""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_api_key(settings: Settings, provided_key: str) -> str | None:
    """常量时间校验 API Key，并返回对应 fingerprint。"""
    if not provided_key:
        return None
    for allowed_key in settings.allowed_api_keys:
        if secrets.compare_digest(provided_key, allowed_key):
            return api_key_fingerprint(allowed_key)
    return None


def issue_session_token(settings: Settings, subject: str) -> str:
    """签发包含过期时间和 HMAC 签名的轻量会话令牌。"""
    payload = json.dumps(
        {
            "sub": subject,
            "exp": int(time.time()) + settings.session_ttl_seconds,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(
        settings.session_secret_key.encode("utf-8"),
        encoded,
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded.decode('ascii')}.{signature}"


def verify_session_token(settings: Settings, token: str) -> str | None:
    """验证签名、有效期以及 API Key 是否仍然有效。"""
    encoded, separator, signature = token.partition(".")
    if not separator or not encoded or not signature:
        return None

    try:
        encoded_bytes = encoded.encode("ascii")
        provided_signature = bytes.fromhex(signature)
    except (UnicodeEncodeError, ValueError):
        return None
    expected = hmac.new(
        settings.session_secret_key.encode("utf-8"),
        encoded_bytes,
        hashlib.sha256,
    ).digest()
    if not secrets.compare_digest(provided_signature, expected):
        return None

    try:
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        subject = payload["sub"]
        expires_at = payload["exp"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(subject, str) or not isinstance(expires_at, int):
        return None
    if expires_at <= int(time.time()):
        return None
    valid_subjects = {api_key_fingerprint(allowed_key) for allowed_key in settings.allowed_api_keys}
    return subject if subject in valid_subjects else None


def resolve_identity(request: Request, settings: Settings) -> AuthIdentity | None:
    """优先使用 API Key，其次使用浏览器 HttpOnly 会话 Cookie。"""
    provided_key = request.headers.get("x-api-key", "")
    fingerprint = verify_api_key(settings, provided_key)
    if fingerprint is not None:
        return AuthIdentity(subject=fingerprint, method="api_key")

    session_token = request.cookies.get(settings.session_cookie_name, "")
    subject = verify_session_token(settings, session_token)
    if subject is not None:
        return AuthIdentity(subject=subject, method="session")
    return None


def client_ip(request: Request, settings: Settings) -> str:
    """仅在受控反向代理后读取转发头，防止客户端伪造来源 IP。"""
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            candidate = forwarded_for.split(",", 1)[0].strip()
            if candidate:
                return candidate
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip
    return request.client.host if request.client else "unknown"
