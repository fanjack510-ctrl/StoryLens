"""Provider transport error taxonomy and safe message helpers (Phase 1C-A.5)."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

import httpx

TRANSPORT_DNS = "dns_error"
TRANSPORT_CONNECT_TIMEOUT = "connect_timeout"
TRANSPORT_CONNECTION = "connection_error"
TRANSPORT_TLS = "tls_error"
TRANSPORT_PROXY = "proxy_error"
TRANSPORT_READ_TIMEOUT = "read_timeout"
TRANSPORT_WRITE_TIMEOUT = "write_timeout"
TRANSPORT_PROTOCOL = "protocol_error"
TRANSPORT_REMOTE_DISCONNECT = "remote_disconnect"
TRANSPORT_INVALID_URL = "invalid_url"
TRANSPORT_HTTP = "http_error"
TRANSPORT_UNKNOWN = "unknown_transport_error"
TRANSPORT_DISABLED = "provider_disabled"
TRANSPORT_AUTH = "authentication_failed"

TRANSPORT_KINDS = {
    TRANSPORT_DNS,
    TRANSPORT_CONNECT_TIMEOUT,
    TRANSPORT_CONNECTION,
    TRANSPORT_TLS,
    TRANSPORT_PROXY,
    TRANSPORT_READ_TIMEOUT,
    TRANSPORT_WRITE_TIMEOUT,
    TRANSPORT_PROTOCOL,
    TRANSPORT_REMOTE_DISCONNECT,
    TRANSPORT_INVALID_URL,
    TRANSPORT_HTTP,
    TRANSPORT_UNKNOWN,
    TRANSPORT_DISABLED,
    TRANSPORT_AUTH,
}

_CODE_BY_TRANSPORT = {
    TRANSPORT_DNS: "PROVIDER_DNS_ERROR",
    TRANSPORT_CONNECT_TIMEOUT: "PROVIDER_CONNECT_TIMEOUT",
    TRANSPORT_CONNECTION: "PROVIDER_CONNECTION_ERROR",
    TRANSPORT_TLS: "PROVIDER_TLS_ERROR",
    TRANSPORT_PROXY: "PROVIDER_PROXY_ERROR",
    TRANSPORT_READ_TIMEOUT: "PROVIDER_READ_TIMEOUT",
    TRANSPORT_WRITE_TIMEOUT: "PROVIDER_WRITE_TIMEOUT",
    TRANSPORT_PROTOCOL: "PROVIDER_PROTOCOL_ERROR",
    TRANSPORT_REMOTE_DISCONNECT: "PROVIDER_REMOTE_DISCONNECT",
    TRANSPORT_INVALID_URL: "PROVIDER_INVALID_URL",
    TRANSPORT_HTTP: "PROVIDER_HTTP_ERROR",
    TRANSPORT_UNKNOWN: "PROVIDER_TRANSPORT_ERROR",
    TRANSPORT_DISABLED: "PROVIDER_DISABLED",
    TRANSPORT_AUTH: "PROVIDER_AUTHENTICATION_FAILED",
}

_DEFAULT_MESSAGES = {
    TRANSPORT_DNS: "DNS解析失败，无法解析Provider主机名",
    TRANSPORT_CONNECT_TIMEOUT: "连接Provider超时",
    TRANSPORT_CONNECTION: "无法建立到Provider的TCP连接",
    TRANSPORT_TLS: "TLS握手或证书校验失败",
    TRANSPORT_PROXY: "代理连接失败",
    TRANSPORT_READ_TIMEOUT: "读取Provider响应超时",
    TRANSPORT_WRITE_TIMEOUT: "向Provider写入请求超时",
    TRANSPORT_PROTOCOL: "与Provider的HTTP协议通信异常",
    TRANSPORT_REMOTE_DISCONNECT: "Provider连接被远端中断",
    TRANSPORT_INVALID_URL: "Provider Base URL无效",
    TRANSPORT_HTTP: "Provider返回HTTP错误",
    TRANSPORT_UNKNOWN: "Provider传输层未知错误",
    TRANSPORT_DISABLED: "Provider已停用，拒绝发送请求",
    TRANSPORT_AUTH: "Provider身份认证失败",
}

_RETRYABLE_TRANSPORT = {
    TRANSPORT_CONNECT_TIMEOUT,
    TRANSPORT_CONNECTION,
    TRANSPORT_READ_TIMEOUT,
    TRANSPORT_WRITE_TIMEOUT,
    TRANSPORT_REMOTE_DISCONNECT,
    TRANSPORT_PROTOCOL,
    TRANSPORT_DNS,  # transient DNS can recover
}

_SENSITIVE = re.compile(
    r"(?i)(Bearer\s+\S+|sk-[A-Za-z0-9._-]+|api[_-]?key\s*[:=]\s*\S+|"
    r"https?://[^\s\"']+|workspace[_-]?id\s*[:=]\s*\S+)"
)


def safe_message(raw: str | None, *, fallback: str) -> str:
    text = (raw or "").strip()
    if not text:
        return fallback
    cleaned = _SENSITIVE.sub("[REDACTED]", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:500] or fallback


def host_fingerprint(host: str | None) -> str | None:
    if not host:
        return None
    digest = hashlib.sha256(host.encode("utf-8")).hexdigest()[:12]
    return f"host#{digest}"


def redact_endpoint_path(base_url: str, suffix: str = "/chat/completions") -> str:
    try:
        parsed = urlparse(base_url)
        path = (parsed.path or "").rstrip("/")
        if path.endswith("/v1"):
            return f"/.../v1{suffix}"
        if "compatible-mode" in path:
            return f"/.../compatible-mode/v1{suffix}"
        return f"/...{suffix}"
    except Exception:
        return f"/...{suffix}"


def classify_exception(exc: BaseException) -> tuple[str, str | None, bool]:
    """Return (transport_kind, timeout_kind, retryable_default)."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    names = " ".join(type(item).__name__.lower() for item in chain)
    messages = " ".join(str(item).lower() for item in chain)

    if isinstance(exc, httpx.ProxyError) or "proxy" in names:
        return TRANSPORT_PROXY, None, True
    if isinstance(exc, httpx.ConnectTimeout) or "connecttimeout" in names:
        return TRANSPORT_CONNECT_TIMEOUT, "connect", True
    if isinstance(exc, httpx.ReadTimeout) or "readtimeout" in names:
        return TRANSPORT_READ_TIMEOUT, "read", True
    if isinstance(exc, httpx.WriteTimeout) or "writetimeout" in names:
        return TRANSPORT_WRITE_TIMEOUT, "write", True
    if isinstance(exc, httpx.PoolTimeout) or "pooltimeout" in names:
        return TRANSPORT_CONNECT_TIMEOUT, "pool", True
    if isinstance(exc, httpx.UnsupportedProtocol) or "invalid url" in messages:
        return TRANSPORT_INVALID_URL, None, False

    tls_markers = ("ssl", "tls", "certificate", "cert ", "handshake")
    if any(marker in names or marker in messages for marker in tls_markers):
        cert_fail = any(
            marker in messages
            for marker in (
                "certificate verify",
                "certificate_verify",
                "cert verify",
                "self-signed",
                "hostname mismatch",
            )
        )
        return TRANSPORT_TLS, None, not cert_fail

    if isinstance(exc, httpx.ConnectError) or "connecterror" in names:
        if any(marker in messages for marker in ("name or service not known", "getaddrinfo", "nodename", "resolve")):
            return TRANSPORT_DNS, None, True
        return TRANSPORT_CONNECTION, None, True

    if "dns" in names or "gaierror" in names or "getaddrinfo" in messages:
        return TRANSPORT_DNS, None, True

    if isinstance(exc, httpx.RemoteProtocolError) or "remoteprotocol" in names:
        return TRANSPORT_REMOTE_DISCONNECT, None, True
    if isinstance(exc, httpx.ProtocolError) or "protocolerror" in names:
        return TRANSPORT_PROTOCOL, None, True
    if isinstance(exc, httpx.TimeoutException) or "timeout" in names:
        return TRANSPORT_READ_TIMEOUT, "timeout", True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else None
        retryable = status in {429, 500, 502, 503, 504} if status else True
        if status in {401, 403}:
            return TRANSPORT_AUTH, None, False
        return TRANSPORT_HTTP, None, retryable
    if isinstance(exc, (ValueError, httpx.InvalidURL)):
        return TRANSPORT_INVALID_URL, None, False
    return TRANSPORT_UNKNOWN, None, True


def error_code_for_transport(transport_kind: str, http_status: int | None = None) -> str:
    if transport_kind == TRANSPORT_HTTP and http_status in {401, 403}:
        return "PROVIDER_AUTHENTICATION_FAILED"
    if transport_kind == TRANSPORT_HTTP and http_status == 404:
        return "PROVIDER_MODEL_NOT_FOUND"
    return _CODE_BY_TRANSPORT.get(transport_kind, "PROVIDER_TRANSPORT_ERROR")


def default_message_for(transport_kind: str, exception_type: str) -> str:
    base = _DEFAULT_MESSAGES.get(transport_kind, _DEFAULT_MESSAGES[TRANSPORT_UNKNOWN])
    return f"{base} ({exception_type})"


def is_retryable(
    transport_kind: str,
    *,
    http_status: int | None = None,
    explicit: bool | None = None,
) -> bool:
    if explicit is not None:
        return explicit
    if http_status in {401, 403}:
        return False
    if http_status in {429, 500, 502, 503, 504}:
        return True
    if transport_kind == TRANSPORT_HTTP:
        return http_status in {429, 500, 502, 503, 504}
    if transport_kind in {TRANSPORT_DISABLED, TRANSPORT_AUTH, TRANSPORT_INVALID_URL}:
        return False
    if transport_kind == TRANSPORT_TLS:
        return True  # temporary handshake; cert verify handled at classify time
    return transport_kind in _RETRYABLE_TRANSPORT


def user_hint_for(transport_kind: str, error_code: str) -> str:
    hints = {
        TRANSPORT_DNS: "检查网络DNS或Base URL主机名后重试；可先运行传输诊断",
        TRANSPORT_CONNECT_TIMEOUT: "检查网络连通性与防火墙后重试；可先运行传输诊断",
        TRANSPORT_CONNECTION: "检查网络、端口443与代理设置；可先运行传输诊断",
        TRANSPORT_TLS: "检查系统时间、代理与CA证书；证书校验失败时勿盲目重试",
        TRANSPORT_PROXY: "检查HTTP(S)_PROXY/NO_PROXY设置后重试",
        TRANSPORT_READ_TIMEOUT: "可稍后重试，或增大Provider超时配置",
        TRANSPORT_WRITE_TIMEOUT: "可稍后重试，或检查上行网络质量",
        TRANSPORT_PROTOCOL: "可重试；若持续失败请查看传输诊断",
        TRANSPORT_REMOTE_DISCONNECT: "可重试；远端可能瞬时断开",
        TRANSPORT_INVALID_URL: "修正Provider Base URL（兼容模式 /v1）后重试",
        TRANSPORT_HTTP: "查看HTTP状态与Provider控制台后处理",
        TRANSPORT_DISABLED: "在“模型与API”启用该Provider后再试",
        TRANSPORT_AUTH: "检查API Key与云端总开关后重试",
        TRANSPORT_UNKNOWN: "先运行传输诊断，确认DNS/TCP/TLS后再重试",
    }
    if error_code == "PROVIDER_MODEL_NOT_FOUND":
        return "检查模型名称配置是否正确"
    return hints.get(transport_kind, "前往“模型与API”运行传输诊断后重试")


def exception_type_name(exc: BaseException) -> str:
    return type(exc).__name__


def original_exception_type(exc: BaseException) -> str:
    root = exc
    while root.__cause__ is not None:
        root = root.__cause__
    return type(root).__name__


def build_safe_details(
    *,
    provider: str,
    model: str | None,
    transport_kind: str,
    exception_type: str,
    original_exception_type_name: str,
    phase: str,
    http_status: int | None,
    timeout_kind: str | None,
    host_hash: str | None,
    request_id: str | None = None,
    provider_request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "transport_kind": transport_kind,
        "exception_type": exception_type,
        "original_exception_type": original_exception_type_name,
        "phase": phase,
        "http_status": http_status,
        "timeout_kind": timeout_kind,
        "host_hash": host_hash,
        "request_id": request_id,
        "provider_request_id": provider_request_id,
    }
