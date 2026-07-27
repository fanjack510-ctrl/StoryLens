"""Reject non-loopback Origins for mutating requests (local web hardening)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


def _extra_allowed_origins() -> set[str]:
    origins: set[str] = set()
    extra = os.environ.get("STORYLENS_ALLOWED_ORIGINS", "")
    for item in extra.split(","):
        item = item.strip().rstrip("/")
        if item:
            origins.add(item)
    return origins


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    h = host.lower().strip("[]")
    return h in {"127.0.0.1", "localhost", "::1"}


def _is_allowed_origin(origin: str) -> bool:
    if origin in {"null", "tauri://localhost", "http://tauri.localhost"}:
        return True
    if origin in _extra_allowed_origins():
        # Extra allowlist still must be loopback or tauri.
        if origin.startswith("tauri://"):
            return True
        try:
            return _is_loopback_host(urlparse(origin).hostname)
        except Exception:  # noqa: BLE001
            return False
    try:
        parsed = urlparse(origin)
    except Exception:  # noqa: BLE001
        return False
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return False
    return _is_loopback_host(parsed.hostname)


class LocalOriginGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)
        origin = request.headers.get("origin")
        if not origin:
            # Same-origin navigations / curl / TestClient often omit Origin.
            return await call_next(request)
        if _is_allowed_origin(origin):
            return await call_next(request)
        return JSONResponse(
            status_code=403,
            content={
                "error_code": "ORIGIN_NOT_ALLOWED",
                "message": "仅允许本机访问 StoryLens 本地服务。",
                "details": {"origin": origin},
            },
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' http://127.0.0.1:* http://localhost:*; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        return response
