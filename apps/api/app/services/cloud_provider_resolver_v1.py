"""Unified cloud provider resolver (CHG-20260808-065).

All new cloud tasks must resolve provider/model through ``resolve_provider_for_task``.
Never silently substitute another formal cloud provider when the selected default
is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProviderConfiguration
from app.services.provider_bootstrap import (
    ensure_aliyun_provider_configuration,
    ensure_deepseek_provider_configuration,
    is_deepseek_provider,
)
from app.services.provider_pricing import DEEPSEEK_DEFAULT_MODEL, DEEPSEEK_PROVIDER
from app.services.provider_runtime import (
    FORMAL_CLOUD_PROVIDERS,
    get_active_cloud_provider,
)
from app.services.task_routing_policy_v1 import (
    RoutingMode,
    get_task_routing_entry,
)


class ResolutionSource(StrEnum):
    RUN_PINNED = "RUN_PINNED"
    TASK_OVERRIDE = "TASK_OVERRIDE"
    USER_DEFAULT = "USER_DEFAULT"
    LOCAL = "LOCAL"


class ProviderResolutionError(Exception):
    """Fail-closed provider resolution — never cross-provider silent fallback."""

    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


@dataclass(frozen=True)
class ProviderResolution:
    provider_name: str
    model_name: str | None
    resolution_source: ResolutionSource
    task_type: str
    routing_mode: RoutingMode
    display_name: str
    policy_label: str


def _default_model_for_provider(session: Session, provider_name: str) -> str:
    row = session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == provider_name)
    )
    if provider_name == "aliyun_qwen_max":
        if row is not None and str(row.max_model or "").strip():
            return str(row.max_model).strip()
        return "qwen3.7-max"
    if row is not None and str(row.plus_model or "").strip():
        return str(row.plus_model).strip()
    if is_deepseek_provider(provider_name):
        return DEEPSEEK_DEFAULT_MODEL
    return "qwen3.7-plus"


def _ensure_row(session: Session, provider_name: str) -> ProviderConfiguration | None:
    name = str(provider_name or "").strip()
    if is_deepseek_provider(name):
        ensure_deepseek_provider_configuration(session, create_if_missing=True)
    elif name.startswith("aliyun_"):
        # Max/Flash share Aliyun credential family via plus row bootstrap + named rows.
        ensure_aliyun_provider_configuration(session, "aliyun_qwen_plus", create_if_missing=True)
        if name != "aliyun_qwen_plus":
            ensure_aliyun_provider_configuration(session, name, create_if_missing=True)
    return session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == name)
    )


def _credential_available(session: Session, provider_name: str) -> bool:
    from app.narrative_core.services.whole_book_active_provider_v1 import (
        provider_credential_available,
    )

    row = _ensure_row(session, provider_name)
    if row is None:
        return False
    return provider_credential_available(session, row)


def assert_formal_provider_available(
    session: Session,
    provider_name: str,
    *,
    require_structured_output: bool = False,
) -> ProviderConfiguration:
    """Validate enabled + credential for a formal cloud provider. No cross-provider substitute."""
    name = str(provider_name or "").strip()
    row = _ensure_row(session, name)
    label = "DeepSeek" if is_deepseek_provider(name) else (
        "阿里云百炼 Max" if name == "aliyun_qwen_max" else "阿里云百炼"
    )
    if row is None:
        raise ProviderResolutionError(
            "DEFAULT_PROVIDER_UNAVAILABLE",
            f"当前默认 AI 服务商 {label} 尚未配置，请前往设置检查。",
            details={"provider_name": name},
        )
    if not bool(row.enabled) or bool(row.disconnected):
        raise ProviderResolutionError(
            "DEFAULT_PROVIDER_UNAVAILABLE",
            f"当前默认 AI 服务商 {label} 不可用，请前往设置检查。",
            details={"provider_name": name, "enabled": bool(row.enabled), "disconnected": bool(row.disconnected)},
        )
    if not _credential_available(session, name):
        raise ProviderResolutionError(
            "DEFAULT_PROVIDER_UNAVAILABLE",
            f"当前默认 AI 服务商 {label} 不可用，请前往设置检查。",
            details={"provider_name": name, "reason": "credential_missing"},
        )
    if require_structured_output and name in FORMAL_CLOUD_PROVIDERS | {"aliyun_qwen_max"}:
        # DeepSeek and Aliyun Plus/Max all support structured JSON in V1.2.0 registry.
        pass
    return row


def resolve_provider_for_task(
    session: Session,
    *,
    task_type: str,
    run_provider_name: str | None = None,
    run_model_name: str | None = None,
    requested_provider: str | None = None,
    requested_model: str | None = None,
    preview: bool = False,
) -> ProviderResolution:
    """Resolve provider/model for a task.

    Priority:
    1. Existing run pin (when policy is INHERIT_RUN, or any task with run pin supplied
       for resume/retry/repair callers)
    2. Task FIXED_PROVIDER / LOCAL_ONLY override
    3. User default (active_cloud_provider + that provider's default model)

    ``preview=True`` softens availability checks so routing UI can still render
    intended targets when keys are missing (``available`` is computed separately).
    """
    entry = get_task_routing_entry(task_type)
    pinned_provider = str(run_provider_name or "").strip() or None
    pinned_model = str(run_model_name or "").strip() or None
    req_provider = str(requested_provider or "").strip() or None
    req_model = str(requested_model or "").strip() or None

    # Priority 1 — run pin for inherit-run tasks (and explicit pin on FOLLOW when provided
    # by resume/repair callers for whole_book_repair / retry).
    if entry.mode == RoutingMode.INHERIT_RUN:
        if not pinned_provider:
            if preview:
                # Preview without a concrete run: advertise policy only (no fake Aliyun target).
                return ProviderResolution(
                    provider_name="(inherit_run)",
                    model_name=None,
                    resolution_source=ResolutionSource.RUN_PINNED,
                    task_type=entry.task_type,
                    routing_mode=entry.mode,
                    display_name=entry.display_name,
                    policy_label="继承当前 Run",
                )
            raise ProviderResolutionError(
                "RUN_PIN_REQUIRED",
                f"任务 {entry.display_name} 必须继承已有 Run 的 Provider/Model，当前缺少 pin。",
                details={"task_type": entry.task_type},
            )
        return ProviderResolution(
            provider_name=pinned_provider,
            model_name=pinned_model or _default_model_for_provider(session, pinned_provider),
            resolution_source=ResolutionSource.RUN_PINNED,
            task_type=entry.task_type,
            routing_mode=entry.mode,
            display_name=entry.display_name,
            policy_label="继承当前 Run",
        )

    # Explicit run pin also wins for FOLLOW_DEFAULT when caller supplies it (resume paths).
    if pinned_provider and entry.mode == RoutingMode.FOLLOW_DEFAULT:
        return ProviderResolution(
            provider_name=pinned_provider,
            model_name=pinned_model or _default_model_for_provider(session, pinned_provider),
            resolution_source=ResolutionSource.RUN_PINNED,
            task_type=entry.task_type,
            routing_mode=entry.mode,
            display_name=entry.display_name,
            policy_label="继承当前 Run",
        )

    if entry.mode == RoutingMode.LOCAL_ONLY:
        name = entry.fixed_provider or "local_qwen14"
        return ProviderResolution(
            provider_name=name,
            model_name=entry.fixed_model,
            resolution_source=ResolutionSource.LOCAL,
            task_type=entry.task_type,
            routing_mode=entry.mode,
            display_name=entry.display_name,
            policy_label="本地模型",
        )

    if entry.mode == RoutingMode.FIXED_PROVIDER:
        name = entry.fixed_provider or ""
        model = entry.fixed_model or _default_model_for_provider(session, name)
        if not preview:
            assert_formal_provider_available(
                session,
                name,
                require_structured_output=entry.requires_structured_output,
            )
        return ProviderResolution(
            provider_name=name,
            model_name=model,
            resolution_source=ResolutionSource.TASK_OVERRIDE,
            task_type=entry.task_type,
            routing_mode=entry.mode,
            display_name=entry.display_name,
            policy_label=f"固定：{name}",
        )

    # FOLLOW_DEFAULT
    active = req_provider or get_active_cloud_provider(session)
    if active not in FORMAL_CLOUD_PROVIDERS and not is_deepseek_provider(active):
        # Refuse unknown cloud defaults — do not coerce to Aliyun.
        raise ProviderResolutionError(
            "DEFAULT_PROVIDER_UNAVAILABLE",
            f"当前默认 AI 服务商 {active} 不受支持，请前往设置检查。",
            details={"provider_name": active},
        )
    if not preview:
        assert_formal_provider_available(
            session,
            active,
            require_structured_output=entry.requires_structured_output,
        )
    model = req_model or _default_model_for_provider(session, active)
    return ProviderResolution(
        provider_name=active,
        model_name=model,
        resolution_source=ResolutionSource.USER_DEFAULT,
        task_type=entry.task_type,
        routing_mode=entry.mode,
        display_name=entry.display_name,
        policy_label="跟随默认",
    )


def build_routing_preview(session: Session, *, gateway_provider_names: set[str]) -> list[dict]:
    """Serialize routing policy for GET /model-routing/preview."""
    from app.services.task_routing_policy_v1 import list_routing_preview_tasks

    rows: list[dict] = []
    for entry in list_routing_preview_tasks():
        try:
            resolved = resolve_provider_for_task(session, task_type=entry.task_type, preview=True)
            provider = resolved.provider_name
            model = resolved.model_name
            policy_label = resolved.policy_label
            source = resolved.resolution_source.value
        except ProviderResolutionError as exc:
            provider = ""
            model = None
            policy_label = exc.message
            source = "ERROR"
        available = bool(provider) and provider in gateway_provider_names
        if provider == "(inherit_run)":
            available = True
        # Soft availability for cloud: also require enabled+key when formal.
        elif available and provider in FORMAL_CLOUD_PROVIDERS | {DEEPSEEK_PROVIDER, "aliyun_qwen_max"}:
            try:
                assert_formal_provider_available(session, provider)
            except ProviderResolutionError:
                available = False
        rows.append(
            {
                "task": entry.display_name,
                "task_type": entry.task_type,
                "provider": provider,
                "model": model,
                "routing_mode": entry.mode.value,
                "policy_label": policy_label,
                "resolution_source": source,
                "available": available,
                "sends_content_to_cloud": entry.mode != RoutingMode.LOCAL_ONLY,
            }
        )
    return rows
