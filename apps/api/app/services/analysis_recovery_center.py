"""Unified Analysis Recovery Center — plan aggregation and idempotent recover."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun,
    ApplicationSetting,
    CloudBudgetReservation,
    Paragraph,
    ProviderConfiguration,
    ReaderJourneyRun,
)
from app.model_gateway.gateway import ModelGateway
from app.schemas.analysis_recovery import (
    AnalysisRecoverRequest,
    AnalysisRecoverResponse,
    AnalysisRecoveryPlanResponse,
    BudgetAuthorizationProposal,
    FullPipelineBudgetAdvisory,
    RecommendedAction,
    RecoveryBlocker,
    RecoveryCheck,
    RecoveryWarning,
    RunBudgetAuthorizationRequest,
)
from app.schemas.settings import CloudBudgetUpdate
from app.services.budget_reservation import active_reservation_totals, available_remaining
from app.services.cloud_budget import daily_usage
from app.services.cloud_pricing import pricing_status
from app.services.credentials.base import CredentialStore
from app.services.provider_runtime_service import ProviderRuntimeService
from app.services.run_scoped_budget_auth import (
    apply_run_budget_auth,
    effective_remaining_with_run_auth,
    load_run_budget_auth,
    load_unified_recover_marker,
    store_unified_recover_marker,
)
from app.services.scene_analysis_progress import (
    load_revision_scenes,
    pending_scenes_for_run,
    scene_analysis_progress,
)
from app.services.staged_budget import (
    BudgetAmounts,
    estimate_stage2_scene_analysis,
    estimate_reader_journey_chapter_synthesis,
    estimate_reader_journey_scene_profiles,
    exceeded_dimensions,
)


USER_STATUS_PAUSED = "paused_recoverable"

# Manual "修复并继续" attempts (separate from transport auto-retry max=3).
MAX_MANUAL_RECOVERY_ATTEMPTS = 5
MAX_AUTO_PROVIDER_RECOVERY_ATTEMPTS = 3

_AUTH_CODES = frozenset(
    {
        "PROVIDER_AUTH_ERROR",
        "PROVIDER_HTTP_401",
        "PROVIDER_HTTP_403",
        "PROVIDER_AUTHENTICATION_FAILED",
        "credential_missing",
        "CREDENTIAL_MISSING",
    }
)

_NON_RETRYABLE_CATEGORIES = frozenset(
    {
        "authentication_error",
        "permission_error",
        "invalid_request",
        "model_or_endpoint_not_found",
    }
)


def _parse_failure_payload(run: AnalysisRun) -> dict[str, Any]:
    raw = run.provider_health_at_failure or ""
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    failure = payload.get("failure")
    return failure if isinstance(failure, dict) else {}


def _provider_error_tech_details(run: AnalysisRun) -> dict[str, Any]:
    failure = _parse_failure_payload(run)
    snapshot = failure.get("http_error_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}
    provider_error = failure.get("provider_error")
    if not isinstance(provider_error, dict):
        provider_error = {}

    def _pick(*keys: str) -> Any:
        for key in keys:
            if snapshot.get(key) is not None:
                return snapshot.get(key)
            if failure.get(key) is not None:
                return failure.get(key)
            if provider_error.get(key) is not None:
                return provider_error.get(key)
        return None

    category = _pick("error_category")
    http_status = _pick("http_status")
    retryable = _pick("retryable")
    if retryable is None:
        retryable = bool(run.retryable)
    return {
        "http_status": http_status,
        "provider_error_code": _pick("provider_error_code"),
        "provider_message": _pick("provider_message", "message"),
        "provider_request_id": _pick("provider_request_id", "request_id"),
        "endpoint_host": _pick("endpoint_host"),
        "error_category": category,
        "retryable": retryable,
        "retry_after": _pick("retry_after"),
        "timeout_stage": _pick("timeout_stage", "timeout_kind"),
        "response_content_type": _pick("response_content_type"),
        "sanitized_response_excerpt": _pick("sanitized_response_excerpt"),
        "occurred_at": _pick("occurred_at"),
        "user_reason": _pick("user_reason"),
    }


def _boundary_user_copy(run: AnalysisRun, tech: dict[str, Any]) -> dict[str, str]:
    """User-facing copy when failure is at boundary detection / provider_request."""
    category = tech.get("error_category")
    from app.model_gateway.provider_errors import user_reason_for_category

    reason = tech.get("user_reason") or user_reason_for_category(
        str(category) if category else None
    )
    return {
        "title": "场景边界识别请求失败",
        "stage_label": "场景边界识别未完成",
        "explanation": "模型服务在识别场景边界时返回错误。已完成的结果将被保留。",
        "reason": reason,
        "impact": "场景边界识别尚未完成，因此暂时无法生成阅读旅程。",
        "config_note": (
            "AI 服务配置正常，但本次场景边界请求失败。"
            if run.root_error_code == "PROVIDER_HTTP_ERROR"
            else "本次场景边界识别未能完成。"
        ),
    }


def _classify_scene_evidence_recovery(
    run: AnalysisRun, tech: dict[str, Any]
) -> dict[str, Any] | None:
    """Map structured evidence / boundary validation failures to recovery actions."""
    from app.services.scene_evidence_validation import user_copy_for_error

    code = str(run.root_error_code or run.error_code or "")
    message = str(
        tech.get("provider_message")
        or tech.get("message")
        or run.error_message
        or ""
    )
    lower = message.lower()

    if code == "SCENE_BOUNDARY_TOO_BROAD" or "scene_boundary_too_broad" in lower:
        copy = user_copy_for_error("SCENE_BOUNDARY_TOO_BROAD")
        return {
            "error_code": "SCENE_BOUNDARY_TOO_BROAD",
            "action": "rerun_scene_boundary",
            "button": copy["button"],
            "repairable": True,
            "user_copy": {
                "title": copy["title"],
                "stage_label": "场景边界需复查",
                "explanation": copy["lead"],
                "reason": "当前场景可能包含多个独立事件",
                "impact": "需要重新检查场景边界后才能可靠映射证据。",
            },
        }

    overbroad_codes = {
        "EVIDENCE_OVERBROAD_REUSE",
        "EVIDENCE_OUTSIDE_SCENE",
        "EVIDENCE_MISSING",
        "EVIDENCE_VALIDATION_FAILED",
    }
    legacy_overbroad = (
        "must not cite the whole scene" in lower
        or "reuse full-scene evidence" in lower
        or "indiscriminately" in lower
    )
    if code in overbroad_codes or legacy_overbroad:
        mapped = (
            code
            if code in {"EVIDENCE_OVERBROAD_REUSE", "EVIDENCE_OUTSIDE_SCENE", "EVIDENCE_MISSING"}
            else "EVIDENCE_OVERBROAD_REUSE"
        )
        copy = user_copy_for_error(mapped)
        return {
            "error_code": mapped,
            "action": "evidence_remap_repair",
            "button": copy["button"] or "整理证据并继续",
            "repairable": True,
            "user_copy": {
                "title": copy["title"],
                "stage_label": "场景证据需整理",
                "explanation": copy["lead"],
                "reason": "部分判断引用了过大的正文范围或证据不合法",
                "impact": "将只整理当前失败场景的证据，不会重复分析已完成场景。",
            },
        }

    # Non-repairable business validation (not evidence-coded): no fix button.
    if run.retryable is False and code == "BUSINESS_VALIDATION_FAILED":
        return {
            "error_code": code,
            "action": "view_error_details",
            "button": "查看问题",
            "repairable": False,
            "user_copy": {
                "title": "分析未完成",
                "stage_label": "业务校验未通过",
                "explanation": "当前问题无法通过自动修复继续。已完成的分析结果会被保留。",
                "reason": "业务校验失败且不可自动修复",
                "impact": "请查看问题详情，或稍后在任务中心处理。",
            },
        }
    return None


def _budget_settings(session: Session) -> tuple[bool, dict[str, Any]]:
    cloud_row = session.get(ApplicationSetting, "cloud_enabled")
    budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
    cloud_enabled = bool(json.loads(cloud_row.value_json)) if cloud_row else False
    budget = CloudBudgetUpdate.model_validate(
        json.loads(budget_row.value_json) if budget_row else {}
    ).model_dump()
    return cloud_enabled, budget


def _remaining_budget(session: Session, run: AnalysisRun | None = None) -> BudgetAmounts:
    cloud_enabled, budget = _budget_settings(session)
    usage = daily_usage(
        session, budget, cloud_enabled, pricing_status(Path("config/cloud_pricing.json"))
    )
    active_req, active_tok, active_cost = active_reservation_totals(session)
    remaining = available_remaining(
        remaining_requests=usage["remaining_requests"],
        remaining_tokens=usage["remaining_tokens"],
        remaining_cost=usage["remaining_estimated_cost"],
        reserved_requests=active_req,
        reserved_tokens=active_tok,
        reserved_cost=active_cost,
    )
    return effective_remaining_with_run_auth(run, remaining)


def _request_hash(run: AnalysisRun) -> str:
    raw = f"{run.id}:{run.provider}:{run.model}:{run.status}:{run.error_code or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _provider_row(session: Session, provider_name: str) -> ProviderConfiguration | None:
    return session.scalar(
        select(ProviderConfiguration).where(
            ProviderConfiguration.provider_name == provider_name
        )
    )


def _journey_for_run(session: Session, run_id: int) -> ReaderJourneyRun | None:
    from app.services.reader_journey_progress import find_recoverable_journey_run

    recoverable = find_recoverable_journey_run(session, run_id)
    if recoverable is not None:
        return recoverable
    return session.scalar(
        select(ReaderJourneyRun)
        .where(ReaderJourneyRun.analysis_run_id == run_id)
        .order_by(desc(ReaderJourneyRun.id))
    )


def _estimate_remaining_work(
    session: Session, run: AnalysisRun
) -> tuple[BudgetAmounts, BudgetAmounts, str, list[str]]:
    """Return (expected, worst, resume_stage, will_reuse)."""
    progress = scene_analysis_progress(session, run)
    pricing_path = Path("config/cloud_pricing.json")
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == int(run.subject_id))
            .order_by(Paragraph.paragraph_index)
        )
    )
    reuse: list[str] = ["AnalysisRun", "BoundaryRevision"]
    if progress.completed_scene_count > 0:
        reuse.append("SceneArtifacts")

    if progress.total_scene_count > 0 and progress.remaining_scene_count > 0:
        pending = pending_scenes_for_run(session, run)
        est = estimate_stage2_scene_analysis(
            session, pending, paragraphs, pricing_path=pricing_path
        )
        return (
            BudgetAmounts(
                est.expected_request_count, est.estimated_total_tokens, est.estimated_cost
            ),
            BudgetAmounts(
                est.worst_case_request_count,
                est.worst_case_total_tokens,
                est.worst_case_cost,
            ),
            "scene_analysis",
            reuse,
        )

    if progress.total_scene_count > 0 and progress.remaining_scene_count == 0:
        reuse = list(dict.fromkeys(reuse + ["SceneArtifacts"]))
        journey = _journey_for_run(session, run.id)
        if journey is not None and journey.status == "succeeded":
            return BudgetAmounts(0, 0, 0.0), BudgetAmounts(0, 0, 0.0), "completed", reuse
        _revision, scenes = load_revision_scenes(session, run)
        scenes = list(scenes)
        if scenes:
            s1 = estimate_reader_journey_scene_profiles(
                scenes, paragraphs, pricing_path=pricing_path
            )
            s2 = estimate_reader_journey_chapter_synthesis(
                scenes, pricing_path=pricing_path
            )
            expected = BudgetAmounts(
                s1.expected_request_count + s2.expected_request_count,
                s1.estimated_total_tokens + s2.estimated_total_tokens,
                round(s1.estimated_cost + s2.estimated_cost, 6),
            )
            worst = BudgetAmounts(
                s1.worst_case_request_count + s2.worst_case_request_count,
                s1.worst_case_total_tokens + s2.worst_case_total_tokens,
                round(s1.worst_case_cost + s2.worst_case_cost, 6),
            )
            return expected, worst, "reader_journey", reuse
        return BudgetAmounts(0, 0, 0.0), BudgetAmounts(0, 0, 0.0), "reader_journey", reuse

    if run.status in {
        "boundary_candidates_partial",
        "failed_provider",
        "failed_structural",
    } or (
        str(run.status).startswith("failed")
        and (run.failed_stage or "")
        in {
            "provider_request",
            "boundary_candidates",
            "boundary_detection",
            "json_validation",
            "schema_validation",
            "structured_output",
            "structural_validation",
            "business_validation",
        }
    ):
        return BudgetAmounts(1, 1000, 0.01), BudgetAmounts(4, 8000, 0.08), "boundary_detection", reuse

    if run.status == "awaiting_boundary_review":
        return BudgetAmounts(0, 0, 0.0), BudgetAmounts(0, 0, 0.0), "boundary_review", reuse

    return BudgetAmounts(0, 0, 0.0), BudgetAmounts(0, 0, 0.0), "none", reuse


def build_full_pipeline_advisory(
    session: Session,
    *,
    paragraph_count: int,
    stage1_expected: int,
    stage1_worst: int,
    stage1_tokens: int,
    stage1_worst_tokens: int,
    stage1_cost: float,
    stage1_worst_cost: float,
    remaining: BudgetAmounts,
) -> FullPipelineBudgetAdvisory:
    """Heuristic full-pipeline advisory before AnalysisRun creation."""
    estimated_scenes = max(1, math.ceil(max(paragraph_count, 8) / 5))
    scene_expected = estimated_scenes
    scene_worst = 2 * estimated_scenes
    rj_batches = math.ceil(estimated_scenes / 2)
    rj_expected = rj_batches + 1
    rj_worst = 2 * rj_batches + 2
    # Safety margins for retry / repair / recovery (not reserved at create).
    retry_margin = max(2, math.ceil(estimated_scenes * 0.25))
    recovery_margin = max(2, math.ceil(estimated_scenes * 0.15))
    full_expected = stage1_expected + scene_expected + rj_expected
    full_worst = stage1_worst + scene_worst + rj_worst + retry_margin + recovery_margin
    # Scale tokens/cost roughly with request ratio from stage1 envelope.
    token_per_req = (stage1_worst_tokens / stage1_worst) if stage1_worst else 1500
    cost_per_req = (stage1_worst_cost / stage1_worst) if stage1_worst else 0.01
    # Prefer estimated-path scaling for hard-gate fields; fall back to worst-case ratio.
    est_token_per_req = (stage1_tokens / stage1_expected) if stage1_expected else token_per_req
    est_cost_per_req = (stage1_cost / stage1_expected) if stage1_expected else cost_per_req
    worst_tokens = int(full_worst * token_per_req)
    worst_cost = round(full_worst * cost_per_req, 6)
    expected_tokens = int(full_expected * est_token_per_req)
    expected_cost = round(full_expected * est_cost_per_req, 6)
    # Hard gate uses estimated (normal path). Worst-case / retry margins are advisory only.
    required = BudgetAmounts(full_expected, expected_tokens, expected_cost)
    exceeded = exceeded_dimensions(required, remaining)
    msg = None
    if exceeded:
        parts = []
        if "requests" in exceeded:
            parts.append(
                f"完整流水线预计约需{full_expected}次请求，当前剩余{remaining.requests}次"
            )
        if "tokens" in exceeded:
            parts.append("Token额度不足以覆盖完整章节流水线预计用量")
        if "estimated_cost" in exceeded:
            parts.append("费用额度不足以覆盖完整章节流水线预计用量")
        msg = "；".join(parts) + "。创建前请先调整额度，避免中途暂停。"
    return FullPipelineBudgetAdvisory(
        boundary_expected_requests=stage1_expected,
        boundary_worst_requests=stage1_worst,
        scene_analysis_expected_requests=scene_expected,
        scene_analysis_worst_requests=scene_worst,
        reader_journey_expected_requests=rj_expected,
        reader_journey_worst_requests=rj_worst,
        retry_repair_margin_requests=retry_margin,
        recovery_margin_requests=recovery_margin,
        full_expected_requests=full_expected,
        full_worst_requests=full_worst,
        retry_reserve_requests=max(0, full_worst - full_expected),
        retry_reserve_tokens=max(0, worst_tokens - expected_tokens),
        retry_reserve_cost=round(max(0.0, worst_cost - expected_cost), 6),
        estimated_tokens=expected_tokens,
        worst_case_tokens=worst_tokens,
        estimated_cost=expected_cost,
        worst_case_cost=worst_cost,
        remaining_requests=remaining.requests,
        remaining_tokens=remaining.tokens,
        remaining_cost=remaining.estimated_cost,
        within_budget=not exceeded,
        exceeded_dimensions=list(exceeded),
        estimated_scene_count=estimated_scenes,
        message=msg,
    )


def build_recovery_plan(
    session: Session,
    run: AnalysisRun,
    gateway: ModelGateway,
    store: CredentialStore,
) -> AnalysisRecoveryPlanResponse:
    progress = scene_analysis_progress(session, run)
    remaining = _remaining_budget(session, run)
    expected, worst, resume_stage, reuse = _estimate_remaining_work(session, run)
    exceeded = exceeded_dimensions(worst, remaining) if worst.requests or worst.tokens else []

    checks: list[RecoveryCheck] = []
    blockers: list[RecoveryBlocker] = []
    warnings: list[RecoveryWarning] = []
    actions: list[RecommendedAction] = []

    # 1) Run status
    terminal_failed = run.status in {"failed", "failed_provider", "failed_structural"} and not (
        run.retryable
        or run.status == "awaiting_provider_recovery"
        or run.failed_stage in {"scene_analysis", "scene_analysis_budget"}
        or run.error_code
        in {"INSUFFICIENT_BUDGET_RESERVATION", "SCENE_ANALYSIS_PROVIDER_RECOVERY"}
    )
    checks.append(
        RecoveryCheck(
            id="run_status",
            label="Run状态",
            status="fail" if terminal_failed and not run.retryable else "pass",
            user_label="任务状态可恢复" if not terminal_failed else "任务不可自动恢复",
            detail=run.status,
            internal_code=run.error_code,
        )
    )

    # 2) Artifact integrity
    scenes_ok = progress.total_scene_count == 0 or (
        progress.completed_scene_count + progress.remaining_scene_count
        == progress.total_scene_count
    )
    scene_complete = bool(
        progress.total_scene_count > 0 and progress.remaining_scene_count == 0
    )
    checks.append(
        RecoveryCheck(
            id="scene_artifacts",
            label="Scene Artifact完整性",
            status="pass" if scenes_ok else "warn",
            user_label=(
                "Scene分析已完成"
                if scene_complete
                else (
                    f"Scene分析进行中（{progress.completed_scene_count}/{progress.total_scene_count}）"
                    if progress.total_scene_count
                    else "尚未固化Scene"
                )
            ),
            detail=(
                f"completed={progress.completed_scene_count} "
                f"remaining={progress.remaining_scene_count} "
                f"total={progress.total_scene_count}"
            ),
        )
    )

    # 3–5) Provider configuration / readiness / connection
    resolved = None
    provider_blockers: list[str] = []
    health_state = "unknown"
    try:
        resolved = ProviderRuntimeService.resolve_for_run(
            gateway, session, run, store, task_type="scene_analysis"
        )
        provider_blockers = list(resolved.eligibility.get("blockers") or [])
        health_state = str(resolved.eligibility.get("health_state") or "unknown")
    except Exception as exc:  # noqa: BLE001 — plan must always return
        provider_blockers = ["provider_resolve_failed"]
        warnings.append(
            RecoveryWarning(code="PROVIDER_RESOLVE_FAILED", message=str(exc)[:200])
        )

    row = _provider_row(session, run.provider)
    disconnected = bool(row.disconnected) if row is not None else False
    credential_missing = "credential_missing" in provider_blockers
    auth_blocked = bool(
        credential_missing
        or (run.root_error_code in _AUTH_CODES)
        or (run.error_code in _AUTH_CODES)
    )
    provider_disconnected = disconnected or "provider_disconnected" in provider_blockers

    if auth_blocked:
        checks.append(
            RecoveryCheck(
                id="credential",
                label="credential",
                status="fail",
                user_label="API Key无效或未配置",
                internal_code="credential_missing"
                if credential_missing
                else (run.root_error_code or "PROVIDER_AUTH_ERROR"),
            )
        )
        blockers.append(
            RecoveryBlocker(
                code="CREDENTIAL_REQUIRED",
                reason="credential_missing"
                if credential_missing
                else "credential_unauthorized",
                user_message="API Key无效或未配置，请前往设置更新密钥",
                provider=run.provider,
                model=run.model,
                settings_focus="api_key",
            )
        )
        actions.append(
            RecommendedAction(
                action="open_settings_api_key",
                label="前往设置更新API Key",
                automatic=False,
            )
        )
    else:
        checks.append(
            RecoveryCheck(
                id="credential",
                label="credential",
                status="pass",
                user_label="凭据已配置",
            )
        )

    if provider_disconnected and not auth_blocked:
        checks.append(
            RecoveryCheck(
                id="provider_connection",
                label="Provider连接",
                status="fail",
                user_label="AI服务暂未连接",
                internal_code="provider_disconnected",
            )
        )
        blockers.append(
            RecoveryBlocker(
                code="PROVIDER_DISCONNECTED",
                reason="provider_disconnected"
                if run.status != "awaiting_provider_recovery"
                else "awaiting_provider_recovery",
                user_message="AI服务暂未连接",
                provider=run.provider,
                model=run.model,
                settings_focus="connection",
            )
        )
        actions.append(
            RecommendedAction(
                action="reconnect_provider",
                label="重新连接AI服务",
                automatic=True,
            )
        )
    else:
        checks.append(
            RecoveryCheck(
                id="provider_connection",
                label="Provider连接",
                status="pass" if not auth_blocked else "skip",
                user_label="AI服务已连接" if not auth_blocked else None,
                detail=health_state,
            )
        )

    # 6) Budgets
    cloud_enabled, budget = _budget_settings(session)
    usage = daily_usage(
        session, budget, cloud_enabled, pricing_status(Path("config/cloud_pricing.json"))
    )
    req_ok = "requests" not in exceeded
    tok_ok = "tokens" not in exceeded
    cost_ok = "estimated_cost" not in exceeded
    checks.append(
        RecoveryCheck(
            id="request_budget",
            label="request budget",
            status="pass" if req_ok else "fail",
            user_label="请求额度充足" if req_ok else "请求额度不足",
            required=worst.requests,
            available=remaining.requests,
            shortfall=max(0, worst.requests - remaining.requests),
            internal_code=None if req_ok else "request_budget_insufficient",
        )
    )
    checks.append(
        RecoveryCheck(
            id="token_budget",
            label="token budget",
            status="pass" if tok_ok else "fail",
            user_label="Token预算充足" if tok_ok else "Token预算不足",
            required=worst.tokens,
            available=remaining.tokens,
            shortfall=max(0, worst.tokens - remaining.tokens),
            internal_code=None if tok_ok else "token_budget_insufficient",
        )
    )
    checks.append(
        RecoveryCheck(
            id="cost_budget",
            label="cost budget",
            status="pass" if cost_ok else "fail",
            user_label="费用预算充足" if cost_ok else "费用预算不足",
            required=worst.estimated_cost,
            available=remaining.estimated_cost,
            shortfall=round(max(0.0, worst.estimated_cost - remaining.estimated_cost), 6),
            internal_code=None if cost_ok else "cost_budget_insufficient",
        )
    )
    if not req_ok:
        blockers.append(
            RecoveryBlocker(
                code="REQUEST_BUDGET_INSUFFICIENT",
                reason="request_budget_insufficient",
                user_message="今日云端请求额度不足",
                required=worst.requests,
                available=remaining.requests,
                shortfall=max(0, worst.requests - remaining.requests),
                settings_focus="budget",
            )
        )
    if not tok_ok:
        blockers.append(
            RecoveryBlocker(
                code="TOKEN_BUDGET_INSUFFICIENT",
                reason="token_budget_insufficient",
                user_message="今日Token预算不足",
                required=worst.tokens,
                available=remaining.tokens,
                shortfall=max(0, worst.tokens - remaining.tokens),
                settings_focus="budget",
            )
        )
    if not cost_ok:
        blockers.append(
            RecoveryBlocker(
                code="COST_BUDGET_INSUFFICIENT",
                reason="cost_budget_insufficient",
                user_message="今日费用预算不足",
                required=worst.estimated_cost,
                available=remaining.estimated_cost,
                shortfall=round(
                    max(0.0, worst.estimated_cost - remaining.estimated_cost), 6
                ),
                settings_focus="budget",
            )
        )

    proposal: BudgetAuthorizationProposal | None = None
    if not req_ok:
        daily_limit = int(budget.get("cloud_daily_request_limit") or 50)
        used = max(0, daily_limit - int(usage.get("remaining_requests") or 0))
        shortfall = max(0, worst.requests - remaining.requests)
        suggested_extra = shortfall
        suggested_limit = max(daily_limit, used + worst.requests)
        suggested_limit = max(suggested_limit, math.ceil((suggested_limit + 10) / 10) * 10)
        proposal = BudgetAuthorizationProposal(
            scope="run_temporary",
            current_daily_request_limit=daily_limit,
            current_remaining_requests=remaining.requests,
            required_requests=worst.requests,
            suggested_extra_requests=suggested_extra,
            suggested_daily_request_limit=suggested_limit,
            estimated_cost=worst.estimated_cost,
            currency="CNY",
            will_not_rerun=["Boundary", "completed Scene Analysis"],
            message=(
                f"当前每日请求保护{daily_limit}次，完成本阶段最坏需要{worst.requests}次；"
                f"建议仅为本次Run临时授权额外{suggested_extra}次请求。"
            ),
        )
        actions.append(
            RecommendedAction(
                action="authorize_run_budget",
                label="仅为本次Run授权额度",
                automatic=False,
                requires_user_authorization=True,
            )
        )

    # Reservation
    reservation = session.scalar(
        select(CloudBudgetReservation)
        .where(CloudBudgetReservation.run_id == run.id)
        .order_by(desc(CloudBudgetReservation.id))
    )
    checks.append(
        RecoveryCheck(
            id="reservation",
            label="Reservation",
            status="pass",
            user_label="预算预留正常"
            if reservation is None or reservation.status != "active"
            else f"存在活跃预留#{reservation.id}",
            detail=reservation.status if reservation else "none",
        )
    )

    # Boundary detection stage check (before journey — journey is a downstream impact)
    tech = _provider_error_tech_details(run)
    boundary_failed = resume_stage == "boundary_detection" or (
        run.failed_stage in {"provider_request", "boundary_detection"}
        and run.status
        in {"failed_provider", "boundary_candidates_partial", "failed", "failed_structural"}
    )
    user_copy = _boundary_user_copy(run, tech) if boundary_failed else None
    if boundary_failed:
        checks.append(
            RecoveryCheck(
                id="boundary_detection",
                label="BoundaryDetection",
                status="fail",
                user_label=user_copy["stage_label"] if user_copy else "场景边界识别未完成",
                detail=run.failed_stage,
                internal_code=run.root_error_code or run.error_code,
            )
        )
        if tech.get("error_category") in _NON_RETRYABLE_CATEGORIES or (
            tech.get("http_status") in {400, 401, 403, 404}
        ):
            blockers.append(
                RecoveryBlocker(
                    code="PROVIDER_REQUEST_NOT_RETRYABLE",
                    reason="provider_request_not_retryable",
                    user_message=(user_copy["reason"] if user_copy else "请求参数或凭据不被接受"),
                    provider=run.provider,
                    model=run.model,
                    settings_focus=(
                        "api_key"
                        if tech.get("error_category")
                        in {"authentication_error", "permission_error"}
                        else "connection"
                    ),
                )
            )

    # Reader journey
    journey = _journey_for_run(session, run.id)
    journey_needed = scene_complete and (
        journey is None
        or journey.status
        not in {"succeeded", "queued", "scene_profiles_running", "chapter_synthesis_running"}
    )
    if scene_complete and (journey is None or journey.status != "succeeded"):
        checks.append(
            RecoveryCheck(
                id="reader_journey",
                label="ReaderJourneyRun",
                status="fail"
                if journey is None
                or journey.status in {"failed", "cancelled", "scene_profiles_partial"}
                else "warn",
                user_label="阅读旅程尚未生成"
                if journey is None
                else f"阅读旅程状态：{journey.status}",
                internal_code="awaiting_reader_journey",
            )
        )
        if journey_needed and not blockers:
            blockers.append(
                RecoveryBlocker(
                    code="AWAITING_READER_JOURNEY",
                    reason="awaiting_reader_journey",
                    user_message="阅读旅程尚未生成",
                )
            )
            actions.append(
                RecommendedAction(
                    action="start_reader_journey",
                    label="继续生成阅读旅程",
                    automatic=True,
                )
            )
    else:
        # Downstream impact only — never present as the root failure check.
        checks.append(
            RecoveryCheck(
                id="reader_journey",
                label="ReaderJourneyRun",
                status="pass" if journey and journey.status == "succeeded" else "skip",
                user_label=(
                    "阅读旅程已完成"
                    if journey and journey.status == "succeeded"
                    else (
                        "后续影响：暂时无法生成阅读旅程"
                        if boundary_failed
                        else "阅读旅程尚未到生成阶段"
                    )
                ),
            )
        )

    # Duplicate run risk (boundary recovery creating new run)
    existing_recovery = session.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.recovered_from_run_id == run.id,
            AnalysisRun.status.in_(
                [
                    "queued",
                    "running",
                    "boundary_candidates_running",
                    "boundary_candidates_partial",
                    "awaiting_boundary_review",
                    "boundary_confirmed",
                    "boundary_confirmed_budget_blocked",
                    "scene_analysis_running",
                    "succeeded",
                ]
            ),
        )
        .order_by(desc(AnalysisRun.id))
    )
    duplicate_risk = existing_recovery is not None
    if duplicate_risk and existing_recovery is not None:
        warnings.append(
            RecoveryWarning(
                code="RECOVERY_RUN_EXISTS",
                message=f"已存在恢复Run #{existing_recovery.id}",
            )
        )

    marker = load_unified_recover_marker(run)
    recovery_attempts = int((marker or {}).get("recovery_attempts") or 0)
    manual_attempts = int((marker or {}).get("manual_recovery_attempts") or recovery_attempts or 0)
    auto_attempts = int((marker or {}).get("auto_recovery_attempts") or 0)
    if run.status == "awaiting_provider_recovery":
        from app.services.scene_analysis_provider_recovery import load_recovery_state

        state = load_recovery_state(run)
        auto_attempts = max(auto_attempts, int(state.get("recovery_cycles") or 0))
        recovery_attempts = max(recovery_attempts, auto_attempts)

    will_create: list[str] = []
    if resume_stage == "reader_journey" and journey is None:
        will_create.append("ReaderJourneyRun")
    if resume_stage == "boundary_detection" and existing_recovery is None:
        will_create.append("AnalysisRun(recovery)")

    provider_not_retryable = bool(
        tech.get("error_category") in _NON_RETRYABLE_CATEGORIES
        or tech.get("http_status") in {400, 401, 403, 404}
        or (run.retryable is False and run.root_error_code == "PROVIDER_HTTP_ERROR")
    )
    recovery_exhausted = manual_attempts >= MAX_MANUAL_RECOVERY_ATTEMPTS or (
        auto_attempts >= MAX_AUTO_PROVIDER_RECOVERY_ATTEMPTS
        and run.status == "awaiting_provider_recovery"
    )

    evidence_error = _classify_scene_evidence_recovery(run, tech)
    if evidence_error and user_copy is None:
        user_copy = evidence_error["user_copy"]

    if recovery_exhausted:
        actions = [
            RecommendedAction(
                action="revalidate_ai_service",
                label="重新验证 AI 服务",
                automatic=False,
            ),
            RecommendedAction(
                action="create_new_recovery_task",
                label="新建恢复任务",
                automatic=False,
            ),
            RecommendedAction(
                action="view_error_details",
                label="查看错误详情",
                automatic=False,
            ),
            RecommendedAction(
                action="handle_later",
                label="稍后处理",
                automatic=False,
            ),
        ]
    elif provider_not_retryable:
        actions = [
            a
            for a in actions
            if a.action
            not in {
                "fix_and_continue",
                "start_reader_journey",
                "reconnect_provider",
            }
        ]
        actions.insert(
            0,
            RecommendedAction(
                action="check_model_config",
                label="检查模型配置",
                automatic=False,
            ),
        )
        actions.append(
            RecommendedAction(
                action="validate_and_save_provider",
                label="验证并保存",
                automatic=False,
            )
        )
        actions.append(
            RecommendedAction(
                action="view_error_details",
                label="查看技术详情",
                automatic=False,
            )
        )
    elif evidence_error:
        # Replace generic “修复并继续” with structured evidence / boundary actions.
        actions = [
            a
            for a in actions
            if a.action
            not in {
                "fix_and_continue",
                "start_reader_journey",
            }
        ]
        if evidence_error["repairable"]:
            actions.insert(
                0,
                RecommendedAction(
                    action=evidence_error["action"],
                    label=evidence_error["button"],
                    automatic=False,
                )
            )
        else:
            actions.insert(
                0,
                RecommendedAction(
                    action="view_error_details",
                    label="查看问题",
                    automatic=False,
                )
            )
            actions.append(
                RecommendedAction(
                    action="handle_later",
                    label="稍后处理",
                    automatic=False,
                )
            )
            actions.append(
                RecommendedAction(
                    action="return_task_center",
                    label="返回任务中心",
                    automatic=False,
                )
            )
    elif not any(a.action == "fix_and_continue" for a in actions):
        # Non-retryable business validation must not show misleading fix_and_continue.
        non_repairable_business = (
            run.retryable is False
            and run.root_error_code == "BUSINESS_VALIDATION_FAILED"
            and not evidence_error
        )
        if not non_repairable_business:
            actions.insert(
                0,
                RecommendedAction(
                    action="fix_and_continue",
                    label="修复并继续",
                    automatic=False,
                    requires_user_authorization=bool(proposal),
                )
            )
        else:
            actions.insert(
                0,
                RecommendedAction(
                    action="view_error_details",
                    label="查看问题",
                    automatic=False,
                )
            )
            actions.append(
                RecommendedAction(
                    action="handle_later",
                    label="稍后处理",
                    automatic=False,
                )
            )
            actions.append(
                RecommendedAction(
                    action="return_task_center",
                    label="返回任务中心",
                    automatic=False,
                )
            )

    hard_blockers = [b for b in blockers if b.severity == "block"]
    recoverable = True
    if auth_blocked and credential_missing is False and run.root_error_code in {
        "PROVIDER_HTTP_401",
        "PROVIDER_HTTP_403",
        "PROVIDER_AUTH_ERROR",
        "PROVIDER_AUTHENTICATION_FAILED",
    }:
        recoverable = True
    if terminal_failed and not hard_blockers and resume_stage == "none":
        recoverable = False
    if provider_not_retryable and resume_stage == "boundary_detection":
        recoverable = True
    if recovery_exhausted:
        recoverable = False

    pause_reason: str | None = None
    if hard_blockers:
        pause_reason = str(hard_blockers[0].reason)
    elif run.status == "awaiting_provider_recovery":
        pause_reason = "awaiting_provider_recovery"
    elif boundary_failed:
        pause_reason = "detection_checkpoint_pending"
    elif journey_needed:
        pause_reason = "awaiting_reader_journey"

    user_status: str
    if run.status == "succeeded" and journey and journey.status == "succeeded":
        user_status = "succeeded"
        recoverable = False
        pause_reason = None
    elif run.status in {
        "queued",
        "running",
        "boundary_candidates_running",
        "scene_analysis_running",
    }:
        user_status = "running"
    elif recovery_exhausted and not hard_blockers:
        user_status = "failed"
    elif hard_blockers or pause_reason:
        user_status = USER_STATUS_PAUSED
    elif not recoverable:
        user_status = "failed"
    else:
        user_status = USER_STATUS_PAUSED if resume_stage not in {"none", "completed"} else "idle"

    retry_eligible = bool(run.retryable) and not provider_not_retryable and not recovery_exhausted

    return AnalysisRecoveryPlanResponse(
        run_id=run.id,
        chapter_id=int(run.subject_id) if str(run.subject_id).isdigit() else None,
        status=run.status,
        user_status=user_status,  # type: ignore[arg-type]
        pause_reason=pause_reason,
        recoverable=recoverable and user_status != "failed",
        blockers=hard_blockers,
        warnings=warnings,
        checks=checks,
        recommended_actions=actions,
        resume_stage=resume_stage,  # type: ignore[arg-type]
        will_reuse_artifacts=reuse,
        will_create_entities=will_create,
        estimated_requests=expected.requests,
        estimated_tokens=expected.tokens,
        estimated_cost=expected.estimated_cost,
        currency="CNY",
        provider=run.provider,
        model=run.model,
        request_hash=_request_hash(run),
        recovery_attempts=recovery_attempts,
        budget_authorization_proposal=proposal if not recovery_exhausted else None,
        details={
            "error_code": run.error_code,
            "root_error_code": run.root_error_code,
            "failed_stage": run.failed_stage,
            "worst_case_requests": worst.requests,
            "worst_case_tokens": worst.tokens,
            "worst_case_cost": worst.estimated_cost,
            "remaining": {
                "requests": remaining.requests,
                "tokens": remaining.tokens,
                "estimated_cost": remaining.estimated_cost,
            },
            "run_scoped_auth": load_run_budget_auth(run),
            "provider_state_version": (
                resolved.provider_state_version if resolved else None
            ),
            "health_state": health_state,
            "completed_scene_count": progress.completed_scene_count,
            "total_scene_count": progress.total_scene_count,
            "remaining_scene_count": progress.remaining_scene_count,
            "manual_recovery_attempts": manual_attempts,
            "auto_recovery_attempts": auto_attempts,
            "max_manual_recovery_attempts": MAX_MANUAL_RECOVERY_ATTEMPTS,
            "max_auto_recovery_attempts": MAX_AUTO_PROVIDER_RECOVERY_ATTEMPTS,
            "recovery_exhausted": recovery_exhausted,
            "provider_not_retryable": provider_not_retryable,
            "evidence_error": (
                {
                    "error_code": evidence_error["error_code"],
                    "action": evidence_error["action"],
                    "repairable": evidence_error["repairable"],
                }
                if evidence_error
                else None
            ),
            "user_error": user_copy,
            "http_status": tech.get("http_status"),
            "provider_error_code": tech.get("provider_error_code"),
            "provider_message": tech.get("provider_message"),
            "provider_request_id": tech.get("provider_request_id"),
            "endpoint_host": tech.get("endpoint_host"),
            "error_category": tech.get("error_category"),
            "retryable": tech.get("retryable"),
            "retry_after": tech.get("retry_after"),
            "timeout_stage": tech.get("timeout_stage"),
            "response_content_type": tech.get("response_content_type"),
            "sanitized_response_excerpt": tech.get("sanitized_response_excerpt"),
            "occurred_at": tech.get("occurred_at"),
            "user_reason": tech.get("user_reason"),
        },
        active_task=resume_stage if user_status == "running" else None,
        duplicate_risk=duplicate_risk,
        existing_recovery_run_id=existing_recovery.id if existing_recovery else None,
        reader_journey_run_id=journey.id if journey else None,
        reader_journey_status=journey.status if journey else None,
        current_stage=resume_stage,
        retry_eligible=retry_eligible,
        reservation_status=reservation.status if reservation else None,
    )


def execute_unified_recover(
    session: Session,
    run: AnalysisRun,
    request: AnalysisRecoverRequest,
    gateway: ModelGateway,
    store: CredentialStore,
    *,
    background_resume_scene: Any | None = None,
    background_start_journey: Any | None = None,
    background_resume_boundary: Any | None = None,
) -> AnalysisRecoverResponse:
    """Execute recovery plan steps in fixed order. Idempotent on successful resume."""
    plan = build_recovery_plan(session, run, gateway, store)
    marker = load_unified_recover_marker(run)
    resume_actions = {
        "resume_scene_analysis",
        "resume_scene_analysis_deferred",
        "start_or_resume_reader_journey",
        "reader_journey_deferred",
        "resume_boundary_detection",
        "resume_boundary_detection_deferred",
    }
    if marker and marker.get("client_request_id") == request.client_request_id and marker.get(
        "actions"
    ):
        prior = set(marker.get("actions") or [])
        # Completed stage resume → always idempotent.
        if prior & resume_actions:
            return AnalysisRecoverResponse(
                run_id=run.id,
                status=run.status,
                user_status=plan.user_status,
                recoverable=plan.recoverable,
                idempotent_replay=True,
                actions_executed=list(marker.get("actions") or []),
                resume_stage=plan.resume_stage,
                will_reuse_artifacts=plan.will_reuse_artifacts,
                will_create_entities=[],
                estimated_requests=plan.estimated_requests,
                estimated_tokens=plan.estimated_tokens,
                estimated_cost=plan.estimated_cost,
                currency=plan.currency,
                budget_authorization_proposal=plan.budget_authorization_proposal,
                blockers=plan.blockers,
                warnings=plan.warnings,
                checks=plan.checks,
                reader_journey_run_id=plan.reader_journey_run_id,
                created_analysis_run_id=plan.existing_recovery_run_id,
                details={"idempotent": True},
                http_request_sent=False,
                model_invocations_started=True,
            )
        # Non-resume recover (budget auth / reconnect only) remains idempotent.
        # Resume=True with only reconnect/auth actions must fall through so boundary
        # recovery can actually start (fixes silent recovery_attempts loops).
        if not request.resume:
            return AnalysisRecoverResponse(
                run_id=run.id,
                status=run.status,
                user_status=plan.user_status,
                recoverable=plan.recoverable,
                idempotent_replay=True,
                actions_executed=list(marker.get("actions") or []),
                resume_stage=plan.resume_stage,
                will_reuse_artifacts=plan.will_reuse_artifacts,
                will_create_entities=[],
                estimated_requests=plan.estimated_requests,
                estimated_tokens=plan.estimated_tokens,
                estimated_cost=plan.estimated_cost,
                currency=plan.currency,
                budget_authorization_proposal=plan.budget_authorization_proposal,
                blockers=plan.blockers,
                warnings=plan.warnings,
                checks=plan.checks,
                reader_journey_run_id=plan.reader_journey_run_id,
                details={"idempotent": True},
                http_request_sent=False,
                model_invocations_started=False,
            )

    if plan.details.get("recovery_exhausted"):
        return AnalysisRecoverResponse(
            run_id=run.id,
            status=run.status,
            user_status="failed",
            recoverable=False,
            actions_executed=[],
            resume_stage=plan.resume_stage,
            will_reuse_artifacts=plan.will_reuse_artifacts,
            will_create_entities=[],
            estimated_requests=plan.estimated_requests,
            estimated_tokens=plan.estimated_tokens,
            estimated_cost=plan.estimated_cost,
            blockers=plan.blockers,
            warnings=plan.warnings,
            checks=plan.checks,
            details={
                **plan.details,
                "recovery_exhausted": True,
                "user_message": "已达到恢复上限，请重新验证 AI 服务或新建恢复任务",
            },
            http_request_sent=False,
            model_invocations_started=False,
        )

    actions_executed: list[str] = []
    created_journey_id = plan.reader_journey_run_id
    created_analysis_run_id = plan.existing_recovery_run_id
    model_started = False
    manual_attempts = int(plan.details.get("manual_recovery_attempts") or 0)
    auto_attempts = int(plan.details.get("auto_recovery_attempts") or 0)

    auth_blocker = next(
        (
            b
            for b in plan.blockers
            if b.reason in {"credential_missing", "credential_unauthorized"}
        ),
        None,
    )
    if auth_blocker:
        return AnalysisRecoverResponse(
            run_id=run.id,
            status=run.status,
            user_status="paused_recoverable",
            recoverable=True,
            actions_executed=[],
            resume_stage=plan.resume_stage,
            will_reuse_artifacts=plan.will_reuse_artifacts,
            will_create_entities=[],
            estimated_requests=plan.estimated_requests,
            estimated_tokens=plan.estimated_tokens,
            estimated_cost=plan.estimated_cost,
            blockers=plan.blockers,
            warnings=plan.warnings,
            checks=plan.checks,
            budget_authorization_proposal=plan.budget_authorization_proposal,
            details={"settings_focus": "api_key", "redirect": "settings_ai_service"},
            http_request_sent=False,
            model_invocations_started=False,
        )

    # Non-retryable provider HTTP: never auto-resume model work.
    if plan.details.get("provider_not_retryable") and request.resume:
        return AnalysisRecoverResponse(
            run_id=run.id,
            status=run.status,
            user_status=plan.user_status,
            recoverable=plan.recoverable,
            actions_executed=[],
            resume_stage=plan.resume_stage,
            will_reuse_artifacts=plan.will_reuse_artifacts,
            will_create_entities=[],
            estimated_requests=plan.estimated_requests,
            estimated_tokens=plan.estimated_tokens,
            estimated_cost=plan.estimated_cost,
            blockers=plan.blockers,
            warnings=plan.warnings,
            checks=plan.checks,
            details={
                **plan.details,
                "resume_blocked": True,
                "user_message": (plan.details.get("user_error") or {}).get("reason")
                or plan.details.get("user_reason")
                or "当前错误不可自动重试，请检查模型配置",
            },
            http_request_sent=False,
            model_invocations_started=False,
        )

    row = _provider_row(session, run.provider)
    if row is not None and row.disconnected:
        row.disconnected = False
        session.commit()
        actions_executed.append("provider_reconnect")
        plan = build_recovery_plan(session, run, gateway, store)
        actions_executed.append("provider_readiness_refresh")

    if request.authorize_budget is not None:
        auth_req: RunBudgetAuthorizationRequest = request.authorize_budget
        if auth_req.scope in {"run_temporary", "global_permanent"}:
            prior = load_run_budget_auth(run)
            already = (
                isinstance(prior, dict)
                and prior.get("client_request_id") == request.client_request_id
                and int(prior.get("extra_requests") or 0) >= int(auth_req.extra_requests or 0)
            )
            apply_run_budget_auth(
                run,
                extra_requests=auth_req.extra_requests,
                extra_tokens=auth_req.extra_tokens,
                extra_cost=auth_req.extra_cost,
                client_request_id=request.client_request_id,
            )
            if auth_req.scope == "global_permanent" and not already:
                _cloud_enabled, budget = _budget_settings(session)
                if auth_req.new_daily_request_limit:
                    budget["cloud_daily_request_limit"] = int(
                        auth_req.new_daily_request_limit
                    )
                    session.merge(
                        ApplicationSetting(
                            key="cloud_budget_settings",
                            value_json=json.dumps(budget, ensure_ascii=False),
                        )
                    )
            session.commit()
            actions_executed.append(
                "run_temporary_request_allowance"
                if auth_req.scope == "run_temporary"
                else "global_budget_update"
            )
            if auth_req.scope == "run_temporary":
                actions_executed.append("run_temporary_budget_authorization")
            plan = build_recovery_plan(session, run, gateway, store)
    elif plan.budget_authorization_proposal and not request.confirmed:
        return AnalysisRecoverResponse(
            run_id=run.id,
            status=run.status,
            user_status="paused_recoverable",
            recoverable=True,
            actions_executed=actions_executed,
            resume_stage=plan.resume_stage,
            will_reuse_artifacts=plan.will_reuse_artifacts,
            will_create_entities=plan.will_create_entities,
            estimated_requests=plan.estimated_requests,
            estimated_tokens=plan.estimated_tokens,
            estimated_cost=plan.estimated_cost,
            budget_authorization_proposal=plan.budget_authorization_proposal,
            blockers=plan.blockers,
            warnings=plan.warnings,
            checks=plan.checks,
            details={"awaiting_budget_authorization": True},
            http_request_sent=False,
            model_invocations_started=False,
        )

    plan = build_recovery_plan(session, run, gateway, store)
    remaining_hard = [
        b
        for b in plan.blockers
        if b.reason
        not in {
            "awaiting_reader_journey",
            "provider_request_not_retryable",
        }
    ]
    if remaining_hard:
        # Soft marker — do not burn manual attempt budget on budget/auth blockers.
        store_unified_recover_marker(
            run,
            client_request_id=request.client_request_id,
            actions=actions_executed,
            resume_stage=plan.resume_stage,
            recovery_attempts=plan.recovery_attempts,
            manual_recovery_attempts=manual_attempts,
            auto_recovery_attempts=auto_attempts,
            last_recovery_kind="partial",
            last_recovery_reason="blockers_remain",
        )
        session.commit()
        return AnalysisRecoverResponse(
            run_id=run.id,
            status=run.status,
            user_status="paused_recoverable",
            recoverable=True,
            actions_executed=actions_executed,
            resume_stage=plan.resume_stage,
            will_reuse_artifacts=plan.will_reuse_artifacts,
            will_create_entities=plan.will_create_entities,
            estimated_requests=plan.estimated_requests,
            estimated_tokens=plan.estimated_tokens,
            estimated_cost=plan.estimated_cost,
            budget_authorization_proposal=plan.budget_authorization_proposal,
            blockers=plan.blockers,
            warnings=plan.warnings,
            checks=plan.checks,
            details={"partial_recovery": True, **plan.details},
            http_request_sent=False,
            model_invocations_started=False,
        )

    if not request.resume or not request.confirmed:
        store_unified_recover_marker(
            run,
            client_request_id=request.client_request_id,
            actions=actions_executed + ["plan_ready"],
            resume_stage=plan.resume_stage,
            recovery_attempts=plan.recovery_attempts,
            manual_recovery_attempts=manual_attempts,
            auto_recovery_attempts=auto_attempts,
            last_recovery_kind="plan_ready",
            last_recovery_reason="awaiting_confirm_resume",
        )
        session.commit()
        return AnalysisRecoverResponse(
            run_id=run.id,
            status=run.status,
            user_status=plan.user_status,
            recoverable=plan.recoverable,
            actions_executed=actions_executed,
            resume_stage=plan.resume_stage,
            will_reuse_artifacts=plan.will_reuse_artifacts,
            will_create_entities=plan.will_create_entities,
            estimated_requests=plan.estimated_requests,
            estimated_tokens=plan.estimated_tokens,
            estimated_cost=plan.estimated_cost,
            blockers=plan.blockers,
            warnings=plan.warnings,
            checks=plan.checks,
            details={"awaiting_confirm_resume": True},
            http_request_sent=False,
            model_invocations_started=False,
        )

    # Manual resume attempt — counted separately from transport auto-retries.
    manual_attempts += 1
    next_attempts = max(plan.recovery_attempts, manual_attempts)

    if plan.resume_stage == "scene_analysis" and background_resume_scene is not None:
        background_resume_scene()
        actions_executed.append("resume_scene_analysis")
        model_started = True
    elif plan.resume_stage == "reader_journey" and background_start_journey is not None:
        jid = background_start_journey()
        if jid:
            created_journey_id = int(jid)
        actions_executed.append("start_or_resume_reader_journey")
        model_started = True
    elif plan.resume_stage == "boundary_detection" and background_resume_boundary is not None:
        created = background_resume_boundary()
        if created:
            created_analysis_run_id = int(created)
            actions_executed.append("resume_boundary_detection")
            model_started = True
        else:
            actions_executed.append("resume_boundary_detection_deferred")
    elif plan.resume_stage == "scene_analysis":
        actions_executed.append("resume_scene_analysis_deferred")
    elif plan.resume_stage == "reader_journey":
        actions_executed.append("reader_journey_deferred")
    elif plan.resume_stage == "boundary_detection":
        actions_executed.append("resume_boundary_detection_deferred")

    store_unified_recover_marker(
        run,
        client_request_id=request.client_request_id,
        actions=actions_executed,
        resume_stage=plan.resume_stage,
        recovery_attempts=next_attempts,
        manual_recovery_attempts=manual_attempts,
        auto_recovery_attempts=auto_attempts,
        last_recovery_kind="manual",
        last_recovery_reason=f"resume:{plan.resume_stage}",
    )
    session.commit()
    final_plan = build_recovery_plan(session, run, gateway, store)
    user_msg = None
    if not model_started and plan.resume_stage == "boundary_detection":
        user_msg = "未能启动场景边界恢复；请查看技术详情后重试"
    return AnalysisRecoverResponse(
        run_id=run.id,
        status=run.status,
        user_status="running" if model_started else final_plan.user_status,
        recoverable=final_plan.recoverable,
        idempotent_replay=False,
        actions_executed=actions_executed,
        resume_stage=final_plan.resume_stage,
        will_reuse_artifacts=final_plan.will_reuse_artifacts,
        will_create_entities=final_plan.will_create_entities,
        estimated_requests=final_plan.estimated_requests,
        estimated_tokens=final_plan.estimated_tokens,
        estimated_cost=final_plan.estimated_cost,
        currency=final_plan.currency,
        blockers=final_plan.blockers,
        warnings=final_plan.warnings,
        checks=final_plan.checks,
        reader_journey_run_id=created_journey_id,
        created_analysis_run_id=created_analysis_run_id,
        details={
            "actions": actions_executed,
            "manual_recovery_attempts": manual_attempts,
            "user_message": user_msg,
            **{k: v for k, v in final_plan.details.items() if k not in {"actions"}},
        },
        http_request_sent=False,
        model_invocations_started=model_started,
    )



__all__ = [
    "build_recovery_plan",
    "build_full_pipeline_advisory",
    "execute_unified_recover",
]
