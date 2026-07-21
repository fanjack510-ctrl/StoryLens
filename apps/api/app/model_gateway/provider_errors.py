"""Provider transport error taxonomy and safe message helpers (Phase 1C-A.5)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

# Provider HTTP / transport error categories (user-facing taxonomy).
ERROR_CATEGORY_AUTHENTICATION = "authentication_error"
ERROR_CATEGORY_PERMISSION = "permission_error"
ERROR_CATEGORY_INVALID_REQUEST = "invalid_request"
ERROR_CATEGORY_MODEL_NOT_FOUND = "model_or_endpoint_not_found"
ERROR_CATEGORY_RATE_LIMITED = "rate_limited"
ERROR_CATEGORY_SERVER = "provider_server_error"
ERROR_CATEGORY_TIMEOUT = "timeout"
ERROR_CATEGORY_NETWORK = "network_error"
ERROR_CATEGORY_INVALID_RESPONSE = "invalid_provider_response"
ERROR_CATEGORY_UNKNOWN = "unknown_provider_error"

RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
NON_RETRYABLE_HTTP_STATUSES = frozenset({400, 401, 403, 404})

_EXCERPT_MAX = 400

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
        retryable = status in RETRYABLE_HTTP_STATUSES if status else True
        if status in {401, 403}:
            return TRANSPORT_AUTH, None, False
        if status == 408:
            return TRANSPORT_READ_TIMEOUT, "http_408", True
        return TRANSPORT_HTTP, None, retryable
    if isinstance(exc, (ValueError, httpx.InvalidURL)):
        return TRANSPORT_INVALID_URL, None, False
    return TRANSPORT_UNKNOWN, None, True


def error_code_for_transport(transport_kind: str, http_status: int | None = None) -> str:
    if transport_kind == TRANSPORT_HTTP and http_status in {401, 403}:
        return "PROVIDER_AUTHENTICATION_FAILED"
    if transport_kind == TRANSPORT_AUTH:
        return "PROVIDER_AUTHENTICATION_FAILED"
    if transport_kind == TRANSPORT_HTTP and http_status == 404:
        return "PROVIDER_MODEL_NOT_FOUND"
    if transport_kind == TRANSPORT_HTTP and http_status == 400:
        return "PROVIDER_HTTP_ERROR"
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
    if http_status in NON_RETRYABLE_HTTP_STATUSES:
        return False
    if http_status in RETRYABLE_HTTP_STATUSES:
        return True
    if transport_kind == TRANSPORT_HTTP:
        return http_status in RETRYABLE_HTTP_STATUSES
    if transport_kind in {TRANSPORT_DISABLED, TRANSPORT_AUTH, TRANSPORT_INVALID_URL}:
        return False
    if transport_kind == TRANSPORT_TLS:
        return True  # temporary handshake; cert verify handled at classify time
    return transport_kind in _RETRYABLE_TRANSPORT


def categorize_provider_error(
    transport_kind: str,
    *,
    http_status: int | None = None,
    timeout_kind: str | None = None,
) -> str:
    """Map transport/HTTP facts to a stable error_category (never invent status)."""
    if http_status == 401 or transport_kind == TRANSPORT_AUTH:
        return ERROR_CATEGORY_AUTHENTICATION
    if http_status == 403:
        return ERROR_CATEGORY_PERMISSION
    if http_status == 400:
        return ERROR_CATEGORY_INVALID_REQUEST
    if http_status == 404:
        return ERROR_CATEGORY_MODEL_NOT_FOUND
    if http_status == 429:
        return ERROR_CATEGORY_RATE_LIMITED
    if http_status in {500, 502, 503, 504}:
        return ERROR_CATEGORY_SERVER
    if http_status == 408 or transport_kind in {
        TRANSPORT_CONNECT_TIMEOUT,
        TRANSPORT_READ_TIMEOUT,
        TRANSPORT_WRITE_TIMEOUT,
    } or timeout_kind:
        return ERROR_CATEGORY_TIMEOUT
    if transport_kind in {
        TRANSPORT_DNS,
        TRANSPORT_CONNECTION,
        TRANSPORT_PROXY,
        TRANSPORT_REMOTE_DISCONNECT,
        TRANSPORT_PROTOCOL,
        TRANSPORT_TLS,
    }:
        return ERROR_CATEGORY_NETWORK
    if transport_kind == TRANSPORT_HTTP and http_status is None:
        return ERROR_CATEGORY_UNKNOWN
    if transport_kind == TRANSPORT_HTTP:
        return ERROR_CATEGORY_UNKNOWN
    return ERROR_CATEGORY_UNKNOWN


def user_reason_for_category(category: str | None) -> str:
    reasons = {
        ERROR_CATEGORY_AUTHENTICATION: "API 凭据无权访问当前模型，或密钥无效",
        ERROR_CATEGORY_PERMISSION: "API 凭据无权访问当前模型",
        ERROR_CATEGORY_INVALID_REQUEST: "请求参数不被当前模型支持",
        ERROR_CATEGORY_MODEL_NOT_FOUND: "当前模型或 Endpoint 不匹配",
        ERROR_CATEGORY_RATE_LIMITED: "请求受到服务商限流",
        ERROR_CATEGORY_SERVER: "模型服务暂时不可用",
        ERROR_CATEGORY_TIMEOUT: "请求超时",
        ERROR_CATEGORY_NETWORK: "网络连接中断或不可达",
        ERROR_CATEGORY_INVALID_RESPONSE: "模型服务返回了无法解析的响应",
        ERROR_CATEGORY_UNKNOWN: "模型服务返回错误",
    }
    return reasons.get(category or "", reasons[ERROR_CATEGORY_UNKNOWN])


def user_hint_for(transport_kind: str, error_code: str, *, category: str | None = None) -> str:
    if category == ERROR_CATEGORY_RATE_LIMITED:
        return "稍后重试；若持续限流请降低并发或检查服务商配额"
    if category == ERROR_CATEGORY_INVALID_REQUEST:
        return "检查模型配置与请求参数；必要时验证并保存后重试"
    if category == ERROR_CATEGORY_MODEL_NOT_FOUND:
        return "检查模型名称与 Endpoint 配置是否正确"
    if category == ERROR_CATEGORY_AUTHENTICATION:
        return "检查 API Key 与云端总开关后重新验证"
    if category == ERROR_CATEGORY_PERMISSION:
        return "确认密钥具备当前模型访问权限"
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


def endpoint_host_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).hostname
        return host or None
    except Exception:
        return None


def parse_retry_after(headers: Any) -> float | None:
    if headers is None:
        return None
    raw = None
    try:
        raw = headers.get("Retry-After") or headers.get("retry-after")
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def extract_provider_error_fields(response: httpx.Response | None) -> dict[str, Any]:
    """Parse provider JSON error body without inventing missing fields."""
    out: dict[str, Any] = {
        "provider_error_code": None,
        "provider_message": None,
        "provider_request_id": None,
        "response_content_type": None,
        "sanitized_response_excerpt": None,
    }
    if response is None:
        return out
    try:
        out["response_content_type"] = response.headers.get("content-type")
    except Exception:
        out["response_content_type"] = None
    text = ""
    try:
        text = response.text or ""
    except Exception:
        text = ""
    out["sanitized_response_excerpt"] = safe_message(text[:_EXCERPT_MAX], fallback="") or None
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            code = err.get("code") or err.get("type") or err.get("error_code")
            msg = err.get("message") or err.get("msg")
            out["provider_error_code"] = str(code) if code is not None else None
            if msg is not None:
                out["provider_message"] = safe_message(str(msg), fallback=str(msg)[:200])
        elif isinstance(err, str):
            out["provider_message"] = safe_message(err, fallback=err[:200])
        code2 = payload.get("code") or payload.get("error_code")
        if out["provider_error_code"] is None and code2 is not None:
            out["provider_error_code"] = str(code2)
        msg2 = payload.get("message") or payload.get("msg")
        if out["provider_message"] is None and msg2 is not None:
            out["provider_message"] = safe_message(str(msg2), fallback=str(msg2)[:200])
        req = (
            payload.get("request_id")
            or payload.get("requestId")
            or (err.get("request_id") if isinstance(err, dict) else None)
        )
        if req is not None:
            out["provider_request_id"] = str(req)
    # Header request id fallback (never invent).
    try:
        header_id = (
            response.headers.get("x-request-id")
            or response.headers.get("x-dashscope-request-id")
            or response.headers.get("request-id")
        )
    except Exception:
        header_id = None
    if out["provider_request_id"] is None and header_id:
        out["provider_request_id"] = str(header_id)
    return out


def build_provider_http_error_snapshot(
    *,
    http_status: int | None,
    transport_kind: str,
    timeout_kind: str | None = None,
    endpoint_host: str | None = None,
    retry_after: float | None = None,
    response: httpx.Response | None = None,
    provider_error_code: str | None = None,
    provider_message: str | None = None,
    provider_request_id: str | None = None,
    response_content_type: str | None = None,
    sanitized_response_excerpt: str | None = None,
    retryable: bool | None = None,
) -> dict[str, Any]:
    extracted = extract_provider_error_fields(response) if response is not None else {
        "provider_error_code": provider_error_code,
        "provider_message": provider_message,
        "provider_request_id": provider_request_id,
        "response_content_type": response_content_type,
        "sanitized_response_excerpt": sanitized_response_excerpt,
    }
    category = categorize_provider_error(
        transport_kind, http_status=http_status, timeout_kind=timeout_kind
    )
    resolved_retryable = (
        retryable
        if retryable is not None
        else is_retryable(transport_kind, http_status=http_status)
    )
    return {
        "http_status": http_status,
        "provider_error_code": extracted.get("provider_error_code") or provider_error_code,
        "provider_message": extracted.get("provider_message") or provider_message,
        "provider_request_id": extracted.get("provider_request_id") or provider_request_id,
        "endpoint_host": endpoint_host,
        "error_category": category,
        "retryable": resolved_retryable,
        "retry_after": retry_after,
        "timeout_stage": timeout_kind,
        "response_content_type": extracted.get("response_content_type") or response_content_type,
        "sanitized_response_excerpt": extracted.get("sanitized_response_excerpt")
        or sanitized_response_excerpt,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "user_reason": user_reason_for_category(category),
    }


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
