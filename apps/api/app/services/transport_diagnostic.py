"""Zero-generation provider transport diagnostics (Phase 1C-A.5)."""

from __future__ import annotations

import os
import socket
import ssl
import time
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.db.models import ProviderConfiguration
from app.model_gateway.base import ModelProvider
from app.model_gateway.provider_errors import host_fingerprint, redact_endpoint_path
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.services.credentials.base import CredentialStore
from app.services.provider_runtime import apply_provider_runtime, cloud_master_enabled


def _probe(status: str, latency_ms: int | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status}
    if latency_ms is not None:
        payload["latency_ms"] = latency_ms
    payload.update(extra)
    return payload


def _proxy_info() -> dict[str, Any]:
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    all_proxy = os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
    no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    detected = bool(http_proxy or https_proxy or all_proxy)
    source = None
    if https_proxy:
        source = "HTTPS_PROXY"
    elif http_proxy:
        source = "HTTP_PROXY"
    elif all_proxy:
        source = "ALL_PROXY"
    return {
        "detected": detected,
        "source": source,
        "no_proxy_includes_localhost": any(
            item.strip() in {"127.0.0.1", "localhost", "::1"}
            for item in no_proxy.split(",")
            if item.strip()
        ),
    }


def _ca_bundle_info() -> dict[str, Any]:
    bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if bundle:
        return {"status": "ok", "source": "env_bundle"}
    try:
        import certifi

        return {"status": "ok", "source": f"certifi:{certifi.where()}"}
    except Exception:
        return {"status": "ok", "source": "system_default"}


def run_transport_diagnostic(
    *,
    provider_name: str,
    provider: ModelProvider,
    session: Session,
    store: CredentialStore,
) -> dict[str, Any]:
    from app.services.provider_bootstrap import (
        ensure_aliyun_provider_configuration,
        is_aliyun_cloud_provider,
    )

    if is_aliyun_cloud_provider(provider_name):
        ensure_aliyun_provider_configuration(session, provider_name)

    apply_provider_runtime(provider, session, store)
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=provider_name)
        .one_or_none()
    )
    master = cloud_master_enabled(session)
    credential_ok = bool(store.get(provider_name)) if store.available() else False
    base_url = ""
    if isinstance(provider, OpenAICompatibleProvider):
        base_url = provider.base_url
    elif row and row.base_url:
        base_url = str(row.base_url)

    configuration_valid = bool(
        isinstance(provider, OpenAICompatibleProvider)
        and provider.enabled
        and base_url
        and credential_ok
        and (not provider.cloud or master)
    )

    dns = _probe("skipped")
    tcp = _probe("skipped")
    tls = _probe("skipped")
    endpoint = {
        "status": "failed",
        "path_redacted": None,
        "scheme_ok": False,
        "port": None,
        "host_hash": None,
        "path_has_v1": False,
        "duplicate_v1": False,
    }
    error_code = None
    hint = None
    overall = "failed"

    try:
        parsed = urlparse(base_url)
        host = parsed.hostname
        scheme_ok = parsed.scheme in {"https", "http"}
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or ""
        path_has_v1 = path.rstrip("/").endswith("/v1") or "/compatible-mode/v1" in path
        duplicate_v1 = path.count("/v1") > 1
        endpoint = {
            "status": "ok" if scheme_ok and host and path_has_v1 and not duplicate_v1 else "failed",
            "path_redacted": redact_endpoint_path(base_url),
            "scheme_ok": scheme_ok,
            "port": port,
            "host_hash": host_fingerprint(host),
            "path_has_v1": path_has_v1,
            "duplicate_v1": duplicate_v1,
        }
        if not scheme_ok or not host:
            error_code = "PROVIDER_INVALID_URL"
            hint = "修正Base URL协议与主机名"
        elif not path_has_v1:
            error_code = "PROVIDER_INVALID_URL"
            hint = "Base URL应包含兼容接口前缀 …/compatible-mode/v1 或 /v1"
        elif duplicate_v1:
            error_code = "PROVIDER_INVALID_URL"
            hint = "Base URL出现重复 /v1，请检查拼接"
        elif not isinstance(provider, OpenAICompatibleProvider) or not provider.enabled:
            error_code = "PROVIDER_DISABLED"
            hint = "在模型与API中启用Provider"
        elif provider.cloud and not master:
            error_code = "CLOUD_MASTER_SWITCH_OFF"
            hint = "打开云端总开关后再诊断连通性"
        elif not credential_ok:
            error_code = "CREDENTIAL_MISSING"
            hint = "配置API Key后再诊断"
        else:
            started = time.perf_counter()
            try:
                socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                dns = _probe("ok", int((time.perf_counter() - started) * 1000))
            except OSError as exc:
                dns = _probe("failed", int((time.perf_counter() - started) * 1000), error=type(exc).__name__)
                error_code = "PROVIDER_DNS_ERROR"
                hint = "检查DNS或主机名"

            if dns["status"] == "ok":
                started = time.perf_counter()
                try:
                    with socket.create_connection((host, port), timeout=10.0):
                        pass
                    tcp = _probe("ok", int((time.perf_counter() - started) * 1000))
                except OSError as exc:
                    tcp = _probe(
                        "failed",
                        int((time.perf_counter() - started) * 1000),
                        error=type(exc).__name__,
                    )
                    error_code = "PROVIDER_CONNECTION_ERROR"
                    hint = "检查网络、防火墙与代理"

            if tcp["status"] == "ok" and parsed.scheme == "https":
                started = time.perf_counter()
                try:
                    context = ssl.create_default_context()
                    with socket.create_connection((host, port), timeout=10.0) as sock:
                        with context.wrap_socket(sock, server_hostname=host) as wrapped:
                            cert = wrapped.getpeercert()
                    tls = _probe(
                        "ok",
                        int((time.perf_counter() - started) * 1000),
                        certificate_valid=bool(cert),
                    )
                except ssl.SSLError as exc:
                    tls = _probe(
                        "failed",
                        int((time.perf_counter() - started) * 1000),
                        certificate_valid=False,
                        error=type(exc).__name__,
                    )
                    error_code = "PROVIDER_TLS_ERROR"
                    hint = "检查系统时间、代理与CA证书"
                except OSError as exc:
                    tls = _probe(
                        "failed",
                        int((time.perf_counter() - started) * 1000),
                        certificate_valid=False,
                        error=type(exc).__name__,
                    )
                    error_code = "PROVIDER_TLS_ERROR"
                    hint = "TLS握手失败，先修复证书或代理"

            if (
                endpoint["status"] == "ok"
                and dns["status"] == "ok"
                and tcp["status"] == "ok"
                and (tls["status"] == "ok" or parsed.scheme != "https")
            ):
                overall = "ok"
                error_code = None
                hint = None
            elif dns["status"] == "ok" or tcp["status"] == "ok":
                overall = "partial"
    except Exception as exc:  # noqa: BLE001 — diagnostic must never raise to caller unexpectedly
        overall = "failed"
        error_code = error_code or "PROVIDER_TRANSPORT_ERROR"
        hint = hint or f"传输诊断异常：{type(exc).__name__}"

    timeout_seconds = (
        provider.timeout_seconds
        if isinstance(provider, OpenAICompatibleProvider)
        else (row.timeout_seconds if row else None)
    )
    connect = min(30, int(timeout_seconds or 30))
    read = int(timeout_seconds or 300)

    return {
        "provider": provider_name,
        "configuration_valid": configuration_valid,
        "provider_enabled": bool(
            isinstance(provider, OpenAICompatibleProvider) and provider.enabled
        ),
        "cloud_master_enabled": master,
        "dns": dns,
        "tcp": tcp,
        "tls": tls,
        "proxy": _proxy_info(),
        "ca_bundle": _ca_bundle_info(),
        "timeout": {
            "total_seconds": read,
            "connect_seconds": connect,
            "read_seconds": read,
            "write_seconds": read,
            "pool_seconds": connect,
        },
        "request_endpoint_shape": endpoint,
        "overall_status": overall,
        "error_code": error_code,
        "user_action_hint": hint,
        "generates_tokens": False,
        "creates_invocation": False,
        "calls_chat_completions": False,
        "note": "传输诊断不会调用模型，不消耗Token。",
    }
