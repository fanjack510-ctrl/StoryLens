"""Unified analysis execution plan for start-analysis gating.

Single backend source of truth shared by Settings readiness and Start Analysis.
Does not call remote models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.db.models import ProviderConfiguration
from app.model_gateway.base import ProviderCapabilities
from app.model_gateway.gateway import ModelGateway
from app.services.ai_validation_snapshot import (
    build_current_fingerprints,
    fingerprints_match,
    load_validation_snapshot,
)
from app.services.credentials.base import CredentialStore
from app.services.provider_eligibility import evaluate_manual_boundary_candidate

AnalysisModeId = Literal["FAST", "BALANCED", "QUALITY", "CUSTOM"]

PIPELINE_STAGES = (
    "scene_boundary_detection",
    "scene_analysis",
    "reader_journey_generation",
    "final_validation",
)

MODE_DEFAULT_MODELS: dict[str, str] = {
    "FAST": "qwen3.6-flash",
    "BALANCED": "qwen3.7-plus",
    "QUALITY": "qwen3.7-max",
}

CANONICAL_PROVIDER_ID = "aliyun_qwen_plus"

REASON_COPY: dict[str, str] = {
    "provider_not_configured": "尚未配置AI服务",
    "credential_missing": "尚未配置 API Key",
    "provider_disabled": "AI 服务未启用",
    "provider_disconnected": "AI 服务尚未连接",
    "cloud_master_switch_off": "云端分析尚未开启",
    "cloud_disabled": "云端分析尚未开启",
    "provider_unhealthy": "Provider暂时不可用，请重新验证连接",
    "provider_health_stale": "服务状态尚未刷新，请点击刷新状态或重新验证",
    "boundary_candidates_not_supported": "当前服务不支持场景边界分析",
    "pricing_unavailable": "计价配置不可用",
    "budget_unavailable": "当前额度不足",
    "validation_not_verified": "AI服务连接未验证",
    "validation_failed": "AI服务连接验证失败",
    "consent_required": "云端发送未确认",
    "stage_model_missing": "当前模式缺少模型",
    "structured_output_unsupported": "当前模型不支持结构化输出",
}


@dataclass
class StageBinding:
    stage: str
    provider_id: str
    model_id: str
    supported: bool
    reason: str | None = None


@dataclass
class AnalysisExecutionPlan:
    mode: str
    selected_provider: str
    selected_model: str
    configured: bool
    credential_available: bool
    connection_verified: bool
    supported_stages: list[str] = field(default_factory=list)
    missing_stages: list[str] = field(default_factory=list)
    stage_bindings: list[StageBinding] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    unsupported_reason: str | None = None
    user_message: str | None = None
    can_start: bool = False
    health_state: str | None = None
    health_source: str | None = None
    provider_state_version: str | None = None
    capability_schema_version: str = "1c-a-2"

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "selected_provider": self.selected_provider,
            "selected_model": self.selected_model,
            "configured": self.configured,
            "credential_available": self.credential_available,
            "connection_verified": self.connection_verified,
            "supported_stages": list(self.supported_stages),
            "missing_stages": list(self.missing_stages),
            "stage_bindings": [
                {
                    "stage": item.stage,
                    "provider_id": item.provider_id,
                    "model_id": item.model_id,
                    "supported": item.supported,
                    "reason": item.reason,
                }
                for item in self.stage_bindings
            ],
            "blockers": list(self.blockers),
            "unsupported_reason": self.unsupported_reason,
            "user_message": self.user_message,
            "can_start": self.can_start,
            "health_state": self.health_state,
            "health_source": self.health_source,
            "provider_state_version": self.provider_state_version,
            "capability_schema_version": self.capability_schema_version,
        }


def _resolve_mode_model(session: Session, mode: str) -> str:
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=CANONICAL_PROVIDER_ID)
        .one_or_none()
    )
    if mode == "CUSTOM":
        return (row.plus_model if row and row.plus_model else MODE_DEFAULT_MODELS["BALANCED"])
    if row and row.plus_model and mode in {"FAST", "BALANCED", "QUALITY"}:
        # Prefer persisted plus_model when settings already applied the preset.
        return row.plus_model
    return MODE_DEFAULT_MODELS.get(mode, MODE_DEFAULT_MODELS["BALANCED"])


def _user_message_for(blockers: list[str]) -> str:
    for code in blockers:
        if code in REASON_COPY:
            return REASON_COPY[code]
    if blockers:
        return REASON_COPY.get(blockers[0], "当前无法开始分析")
    return "可以开始分析"


def build_analysis_execution_plan(
    session: Session,
    *,
    gateway: ModelGateway,
    store: CredentialStore,
    mode: str = "BALANCED",
    pricing_path: Path | None = None,
) -> AnalysisExecutionPlan:
    normalized = (mode or "BALANCED").upper()
    if normalized not in {"FAST", "BALANCED", "QUALITY", "CUSTOM"}:
        normalized = "BALANCED"
    pricing = pricing_path or Path("config/cloud_pricing.json")
    provider = gateway.get(CANONICAL_PROVIDER_ID)
    capabilities: ProviderCapabilities = provider.capabilities()
    model_id = _resolve_mode_model(session, normalized)

    eligibility = evaluate_manual_boundary_candidate(
        session,
        provider_name=CANONICAL_PROVIDER_ID,
        capabilities=capabilities,
        store=store,
        pricing_path=pricing,
    )

    configured = bool(eligibility.get("configured"))
    credential_available = bool(eligibility.get("credential_configured"))
    connection_verified = bool(
        eligibility.get("manual_boundary_candidate_eligible")
        or eligibility.get("health_source") in {"cached_connection_test", "validation_snapshot"}
        and eligibility.get("health_state") == "healthy"
    )
    # Stronger verified signal from durable settings snapshot when present.
    snapshot = load_validation_snapshot(session)
    current_fp = build_current_fingerprints(
        session, store, provider_id=CANONICAL_PROVIDER_ID
    )
    snapshot_ok = bool(
        snapshot
        and snapshot.get("validation_status") == "success"
        and fingerprints_match(snapshot, current_fp)
    )
    if snapshot_ok:
        connection_verified = True

    blockers = list(eligibility.get("manual_selection_blockers") or [])
    if not capabilities.supports_structured_output and "structured_output_unsupported" not in blockers:
        blockers.append("structured_output_unsupported")
    if not snapshot_ok and "provider_unhealthy" not in blockers:
        if not snapshot or snapshot.get("validation_status") != "success":
            if configured and credential_available and "validation_not_verified" not in blockers:
                # Keep eligibility blockers authoritative; only add when nothing else blocks.
                pass

    stage_bindings: list[StageBinding] = []
    supported: list[str] = []
    missing: list[str] = []
    for stage in PIPELINE_STAGES:
        if stage == "scene_boundary_detection":
            ok = bool(capabilities.supports_boundary_candidates)
            reason = None if ok else "boundary_candidates_not_supported"
        elif stage == "scene_analysis":
            ok = bool(capabilities.supports_scene_analysis)
            reason = None if ok else "stage_model_missing"
        elif stage == "reader_journey_generation":
            # Same cloud provider executes journey; no separate registry flag required.
            ok = bool(capabilities.cloud and capabilities.supports_scene_analysis)
            reason = None if ok else "stage_model_missing"
        else:  # final_validation — local deterministic, no model required
            ok = True
            reason = None
        stage_bindings.append(
            StageBinding(
                stage=stage,
                provider_id=CANONICAL_PROVIDER_ID,
                model_id=model_id,
                supported=ok,
                reason=reason,
            )
        )
        if ok:
            supported.append(stage)
        else:
            missing.append(stage)
            if reason and reason not in blockers:
                blockers.append(reason)

    can_start = (
        configured
        and credential_available
        and bool(eligibility.get("enabled"))
        and bool(eligibility.get("connected"))
        and not missing
        and bool(eligibility.get("manual_boundary_candidate_eligible"))
    )
    # Snapshot-verified installs must not remain stuck on stale cached_failure alone.
    if (
        not can_start
        and snapshot_ok
        and configured
        and credential_available
        and bool(eligibility.get("enabled"))
        and bool(eligibility.get("connected"))
        and not missing
        and set(blockers) <= {"provider_unhealthy", "provider_health_stale"}
    ):
        can_start = True
        blockers = []

    user_message = _user_message_for(blockers) if not can_start else "可以开始分析"
    unsupported_reason = blockers[0] if blockers else None

    return AnalysisExecutionPlan(
        mode=normalized,
        selected_provider=CANONICAL_PROVIDER_ID,
        selected_model=model_id,
        configured=configured,
        credential_available=credential_available,
        connection_verified=connection_verified or snapshot_ok,
        supported_stages=supported,
        missing_stages=missing,
        stage_bindings=stage_bindings,
        blockers=blockers,
        unsupported_reason=unsupported_reason,
        user_message=user_message,
        can_start=can_start,
        health_state=str(eligibility.get("health_state") or ""),
        health_source=str(eligibility.get("health_source") or ""),
        provider_state_version=str(eligibility.get("provider_state_version") or ""),
    )
