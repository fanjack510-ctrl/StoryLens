"""Persisted AI model-service validation snapshot (ordinary Settings UI).

Stores probe outcomes in ApplicationSetting (SQLite per environment).
Never stores API keys, Authorization headers, or user document text.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.db.models import ApplicationSetting, ProviderConfiguration
from app.services.credentials.base import CredentialStore

VALIDATION_SNAPSHOT_KEY = "ai_service_validation_snapshot"

ConnectionUiState = Literal[
    "NOT_CONFIGURED",
    "CONFIGURED_NOT_VERIFIED",
    "VERIFIED",
    "CONFIG_CHANGED",
    "VERIFICATION_FAILED",
    "CONSENT_REQUIRED",
    "READY",
]

UI_LABELS: dict[ConnectionUiState, str] = {
    "NOT_CONFIGURED": "尚未配置",
    "CONFIGURED_NOT_VERIFIED": "已配置，尚未验证",
    "VERIFIED": "验证成功",
    "CONFIG_CHANGED": "配置已更改，需要重新验证",
    "VERIFICATION_FAILED": "验证失败",
    "CONSENT_REQUIRED": "连接已验证，分析前需确认正文发送",
    "READY": "可以开始分析",
}

FAILURE_CATEGORY_COPY: dict[str, str] = {
    "CREDENTIAL_INVALID": "API Key无效",
    "RATE_LIMITED": "请求受到服务商限流",
    "MODEL_NOT_AVAILABLE": "模型不存在或无权限",
    "CONNECTION_TEST_FAILED": "网络连接失败",
    "TIMEOUT": "服务响应超时",
    "PROVIDER_ERROR": "服务商返回异常",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_setting(session: Session, key: str, default: Any) -> Any:
    row = session.get(ApplicationSetting, key)
    if row is None:
        return default
    return json.loads(row.value_json)


def _save_setting(session: Session, key: str, value: Any) -> None:
    row = session.get(ApplicationSetting, key)
    payload = json.dumps(value, ensure_ascii=False)
    if row is None:
        session.add(ApplicationSetting(key=key, value_json=payload))
    else:
        row.value_json = payload
        row.updated_at = datetime.now(timezone.utc)
    session.commit()


def endpoint_host(base_url: str | None) -> str:
    raw = (base_url or "").strip()
    if not raw:
        return ""
    try:
        return (urlparse(raw).netloc or raw).lower()
    except Exception:  # noqa: BLE001
        return raw.lower()


def credential_version_fingerprint(store: CredentialStore, provider_id: str) -> str | None:
    secret = store.get(provider_id)
    if not secret:
        return None
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return digest[:32]


def configuration_fingerprint(
    *,
    provider_key: str,
    model_id: str,
    endpoint_host_value: str,
    workspace_id: str,
    allow_auto_route: bool,
    provider_enabled: bool,
    cloud_enabled: bool,
) -> str:
    material = {
        "provider": provider_key,
        "model_id": model_id,
        "endpoint_host": endpoint_host_value,
        "workspace_id": workspace_id or "",
        "routing_mode": "auto" if allow_auto_route else "manual",
        "provider_enabled": bool(provider_enabled),
        "cloud_enabled": bool(cloud_enabled),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]


def build_current_fingerprints(
    session: Session,
    store: CredentialStore,
    *,
    provider_id: str,
    cloud_key: str = "cloud_enabled",
) -> dict[str, Any]:
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=provider_id)
        .one_or_none()
    )
    cloud_enabled = bool(_read_setting(session, cloud_key, False))
    model_id = (row.plus_model if row else None) or "qwen3.7-plus"
    host = endpoint_host(row.base_url if row else None)
    workspace_id = (row.workspace_id if row else None) or ""
    enabled = bool(row.enabled) if row else False
    allow_auto = bool(row.allow_auto_route) if row else False
    cfg_fp = configuration_fingerprint(
        provider_key=provider_id,
        model_id=model_id,
        endpoint_host_value=host,
        workspace_id=workspace_id,
        allow_auto_route=allow_auto,
        provider_enabled=enabled,
        cloud_enabled=cloud_enabled,
    )
    cred_fp = credential_version_fingerprint(store, provider_id)
    return {
        "provider_key": provider_id,
        "provider_display_name": (row.display_name if row else None) or "阿里云百炼",
        "model_id": model_id,
        "endpoint_host": host,
        "workspace_id": workspace_id,
        "provider_enabled": enabled,
        "cloud_enabled": cloud_enabled,
        "configuration_fingerprint": cfg_fp,
        "credential_version_fingerprint": cred_fp,
    }


def load_validation_snapshot(session: Session) -> dict[str, Any] | None:
    raw = _read_setting(session, VALIDATION_SNAPSHOT_KEY, None)
    if not isinstance(raw, dict):
        return None
    # Hard sanitize: never echo secrets if somehow present.
    cleaned = {k: v for k, v in raw.items() if k not in {"api_key", "authorization", "body"}}
    return cleaned


def save_validation_snapshot(session: Session, snapshot: dict[str, Any]) -> dict[str, Any]:
    sanitized = {
        "provider_key": snapshot.get("provider_key"),
        "provider_display_name": snapshot.get("provider_display_name"),
        "model_id": snapshot.get("model_id"),
        "endpoint_host": snapshot.get("endpoint_host"),
        "validation_status": snapshot.get("validation_status"),
        "validated_at": snapshot.get("validated_at") or _now_iso(),
        "failure_category": snapshot.get("failure_category"),
        "failure_message": snapshot.get("failure_message"),
        "provider_request_id": snapshot.get("provider_request_id"),
        "configuration_fingerprint": snapshot.get("configuration_fingerprint"),
        "credential_version_fingerprint": snapshot.get("credential_version_fingerprint"),
        "validation_latency_ms": snapshot.get("validation_latency_ms"),
        "response_model": snapshot.get("response_model"),
        "application_version": snapshot.get("application_version"),
    }
    _save_setting(session, VALIDATION_SNAPSHOT_KEY, sanitized)
    return sanitized


def record_validation_outcome(
    session: Session,
    store: CredentialStore,
    *,
    provider_id: str,
    ok: bool,
    model_name: str | None = None,
    failure_category: str | None = None,
    failure_message: str | None = None,
    provider_request_id: str | None = None,
    validation_latency_ms: int | None = None,
    application_version: str | None = None,
    cloud_key: str = "cloud_enabled",
) -> dict[str, Any]:
    current = build_current_fingerprints(
        session, store, provider_id=provider_id, cloud_key=cloud_key
    )
    snapshot = {
        **current,
        "validation_status": "success" if ok else "failed",
        "validated_at": _now_iso(),
        "failure_category": None if ok else (failure_category or "UNKNOWN"),
        "failure_message": None if ok else (failure_message or "验证失败"),
        "provider_request_id": provider_request_id,
        "validation_latency_ms": validation_latency_ms,
        "response_model": model_name or current.get("model_id"),
        "application_version": application_version,
    }
    return save_validation_snapshot(session, snapshot)


def fingerprints_match(snapshot: dict[str, Any] | None, current: dict[str, Any]) -> bool:
    if not snapshot:
        return False
    return (
        snapshot.get("configuration_fingerprint") == current.get("configuration_fingerprint")
        and snapshot.get("credential_version_fingerprint")
        == current.get("credential_version_fingerprint")
        and snapshot.get("credential_version_fingerprint") is not None
    )


def failure_user_message(category: str | None) -> str:
    if not category:
        return "未知验证错误"
    return FAILURE_CATEGORY_COPY.get(str(category).upper(), "未知验证错误")


def format_validated_at_local(iso_value: str | None) -> str | None:
    if not iso_value:
        return None
    try:
        dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        local = dt.astimezone()
        return local.strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return iso_value[:16].replace("T", " ")


def derive_connection_ui_state(
    *,
    credential_configured: bool,
    provider_enabled: bool,
    cloud_enabled: bool,
    cloud_body_consent: bool,
    provider_eligible: bool,
    snapshot: dict[str, Any] | None,
    current: dict[str, Any],
    provider_display_name: str = "云端模型服务",
) -> tuple[ConnectionUiState, str, str]:
    """Return (state, label, reason).

    `provider_display_name` 是调用方传进来的当前服务商名字。这两句话原本写死「阿里云百炼」，
    于是一个用 DeepSeek 的人会读到「当前配置可以连接阿里云百炼（deepseek-v4-flash）」——
    一句话里两家厂商，而他一家阿里云都没配。
    """
    if not credential_configured:
        return (
            "NOT_CONFIGURED",
            UI_LABELS["NOT_CONFIGURED"],
            "请完成模型服务配置。",
        )

    match = fingerprints_match(snapshot, current)
    status = (snapshot or {}).get("validation_status") if snapshot else None

    if snapshot and status == "failed" and match:
        category = snapshot.get("failure_category")
        reason = failure_user_message(str(category) if category else None)
        when = format_validated_at_local(snapshot.get("validated_at"))
        suffix = f"最近验证失败：{when}" if when else "最近一次验证未通过。"
        return "VERIFICATION_FAILED", reason, suffix

    if snapshot and status == "success" and not match:
        return (
            "CONFIG_CHANGED",
            UI_LABELS["CONFIG_CHANGED"],
            "配置或凭据已变化，请重新验证模型服务。",
        )

    if not snapshot or status != "success" or not match:
        return (
            "CONFIGURED_NOT_VERIFIED",
            UI_LABELS["CONFIGURED_NOT_VERIFIED"],
            "请验证模型服务后再开始分析。",
        )

    # Snapshot success + fingerprints match.
    if not provider_enabled or not cloud_enabled:
        # Fingerprint includes these flags; mismatch normally hits CONFIG_CHANGED.
        # Keep a safe fallback.
        return (
            "CONFIG_CHANGED",
            UI_LABELS["CONFIG_CHANGED"],
            "云端开关或服务启用状态已变化，请重新验证。",
        )

    when = format_validated_at_local(snapshot.get("validated_at"))
    model = snapshot.get("response_model") or snapshot.get("model_id") or current.get("model_id")
    recent = f"最近验证：{when}" if when else "最近一次验证成功。"

    if not cloud_body_consent:
        return (
            "CONSENT_REQUIRED",
            UI_LABELS["CONSENT_REQUIRED"],
            f"勾选正文发送同意后即可开始分析。{recent}",
        )

    if provider_eligible:
        return (
            "READY",
            UI_LABELS["READY"],
            f"当前配置可以连接{provider_display_name}（{model}）。{recent}",
        )

    return (
        "VERIFIED",
        UI_LABELS["VERIFIED"],
        f"当前配置可以连接{provider_display_name}（{model}）。{recent}",
    )


def public_snapshot_view(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snapshot:
        return None
    return {
        "provider_display_name": snapshot.get("provider_display_name"),
        "model_id": snapshot.get("model_id"),
        "response_model": snapshot.get("response_model"),
        "endpoint_host": snapshot.get("endpoint_host"),
        "validation_status": snapshot.get("validation_status"),
        "validated_at": snapshot.get("validated_at"),
        "validated_at_display": format_validated_at_local(snapshot.get("validated_at")),
        "failure_category": snapshot.get("failure_category"),
        "failure_message": snapshot.get("failure_message"),
        "validation_latency_ms": snapshot.get("validation_latency_ms"),
        "application_version": snapshot.get("application_version"),
    }
