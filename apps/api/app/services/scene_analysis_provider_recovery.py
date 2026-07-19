# -*- coding: utf-8 -*-
"""Scene Analysis provider recovery (DEFECT-CANARY-014 / change v1.0.9).

When a single Scene exhausts transport retries with a remote disconnect (or
equivalent retryable transport failure), the AnalysisRun enters a recoverable
pause (``awaiting_provider_recovery``) instead of half-succeeding or forcing a
blind full re-run. Completed Scene Analysis artifacts are permanently reused;
only pending Scenes are retried after circuit-breaker cooldown.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, CloudBudgetReservation, ModelInvocation, Scene
from app.model_gateway.base import ProviderRequestError
from app.model_gateway.transport_retry import NON_RETRYABLE_HTTP_STATUSES
from app.services.scene_analysis_progress import (
    clear_scene_analysis_error_fields,
    scene_analysis_progress,
)
from app.services.scene_pipeline import classify_pipeline_error
from app.services.structured_output import StructuredOutputError

STATUS_AWAITING_PROVIDER_RECOVERY = "awaiting_provider_recovery"
RECOVERY_STATE_KIND = "provider_recovery_state"
RECOVERY_PAUSE_KIND = "awaiting_provider_recovery"
RECOVERY_AUDIT_KIND = "provider_recovery_cycle"

# Transport failures eligible for circuit-breaker recovery.
RECOVERABLE_PROVIDER_CODES = frozenset(
    {
        "PROVIDER_REMOTE_DISCONNECT",
        "PROVIDER_CONNECT_TIMEOUT",
        "PROVIDER_READ_TIMEOUT",
        "PROVIDER_CONNECTION_ERROR",
        "PROVIDER_PROTOCOL_ERROR",
        "PROVIDER_HTTP_429",
        "PROVIDER_HTTP_500",
        "PROVIDER_HTTP_502",
        "PROVIDER_HTTP_503",
        "PROVIDER_HTTP_504",
    }
)

# Validation / business / auth — never enter provider recovery.
NON_RECOVERABLE_CODES = frozenset(
    {
        "PROVIDER_AUTH_ERROR",
        "PROVIDER_HTTP_401",
        "PROVIDER_HTTP_403",
        "PROVIDER_DISABLED",
        "PROVIDER_NOT_CONNECTED",
        "JSON_PARSE_FAILED",
        "SCHEMA_VALIDATION_FAILED",
        "EVIDENCE_VALIDATION_FAILED",
        "BUSINESS_VALIDATION_FAILED",
        "STRUCTURAL_VALIDATION_FAILED",
        "VALIDATION_ERROR",
        "OUTPUT_TRUNCATED",
        "CLOUD_CONSENT_REQUIRED",
        "INSUFFICIENT_BUDGET_RESERVATION",
        "MODEL_INVOCATION_POLICY_VIOLATION",
        "MODEL_PROVIDER_DISABLED_PRECHECK",
        "MODEL_UNAUTHORIZED_FALLBACK",
        "MODEL_INVOCATION_TYPE_UNREGISTERED",
    }
)


@dataclass(frozen=True)
class ProviderRecoveryPolicy:
    max_recovery_cycles: int = 3
    max_recovery_duration_seconds: float = 1800.0
    max_cost: float | None = None
    circuit_cooldown_seconds: float = 15.0


def policy_from_settings(settings: object) -> ProviderRecoveryPolicy:
    max_cost_raw = getattr(settings, "scene_analysis_recovery_max_cost", None)
    max_cost: float | None
    try:
        max_cost = float(max_cost_raw) if max_cost_raw is not None else None
    except (TypeError, ValueError):
        max_cost = None
    return ProviderRecoveryPolicy(
        max_recovery_cycles=max(
            1, int(getattr(settings, "scene_analysis_recovery_max_cycles", 3))
        ),
        max_recovery_duration_seconds=max(
            1.0,
            float(getattr(settings, "scene_analysis_recovery_max_duration_seconds", 1800.0)),
        ),
        max_cost=max_cost,
        circuit_cooldown_seconds=max(
            0.0,
            float(getattr(settings, "scene_analysis_recovery_cooldown_seconds", 15.0)),
        ),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _exc_provider_error(exc: Exception) -> ProviderRequestError | None:
    if isinstance(exc, ProviderRequestError):
        return exc
    if isinstance(exc, StructuredOutputError) and exc.provider_error is not None:
        return exc.provider_error
    return None


def extract_provider_root_code(exc: Exception) -> str:
    root_code, _stage, _retryable, _hint = classify_pipeline_error(exc)
    return str(root_code or "")


def is_provider_transport_recoverable(exc: Exception) -> bool:
    """True only for retryable provider transport failures (not validation/auth)."""
    code = extract_provider_root_code(exc)
    if code in NON_RECOVERABLE_CODES:
        return False
    provider_exc = _exc_provider_error(exc)
    if provider_exc is not None:
        status = getattr(provider_exc, "http_status_code", None)
        if status is not None and int(status) in NON_RETRYABLE_HTTP_STATUSES:
            return False
        if provider_exc.retryable is False:
            return False
        if code.startswith("PROVIDER_") and code in RECOVERABLE_PROVIDER_CODES:
            return True
        if code == "PROVIDER_REMOTE_DISCONNECT":
            return True
        # Unknown PROVIDER_* with retryable=True and transport_kind set.
        if (
            code.startswith("PROVIDER_")
            and provider_exc.retryable
            and provider_exc.transport_kind
            and provider_exc.http_request_sent
        ):
            return code not in NON_RECOVERABLE_CODES
        return False
    if isinstance(exc, StructuredOutputError):
        if exc.category in {
            "json_validation",
            "schema_validation",
            "evidence_validation",
            "business_validation",
            "structural_validation",
        }:
            return False
        if code in NON_RECOVERABLE_CODES:
            return False
    return code in RECOVERABLE_PROVIDER_CODES


def load_recovery_state(run: AnalysisRun) -> dict[str, Any]:
    for source in (run.raw_output, run.provider_health_at_failure):
        if not source:
            continue
        try:
            payload = json.loads(source)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("kind") in {RECOVERY_STATE_KIND, RECOVERY_PAUSE_KIND}:
            return dict(payload)
        nested = payload.get("provider_recovery")
        if isinstance(nested, dict):
            return dict(nested)
    return {}


def _dump_state(run: AnalysisRun, state: dict[str, Any]) -> None:
    text = json.dumps(state, ensure_ascii=False)
    run.raw_output = text
    run.provider_health_at_failure = json.dumps(
        {"provider_recovery": state, "failure": state.get("last_failure")},
        ensure_ascii=False,
    )


def scene_analysis_cost_so_far(session: Session, run_id: int) -> float:
    total = session.scalar(
        select(func.coalesce(func.sum(ModelInvocation.estimated_cost), 0.0)).where(
            ModelInvocation.run_id == run_id,
            ModelInvocation.task_type == "scene_analysis",
        )
    )
    return float(total or 0.0)


def check_recovery_limits(
    session: Session,
    run: AnalysisRun,
    policy: ProviderRecoveryPolicy,
    *,
    next_cycle: int,
    recovery_started_at: datetime | None,
) -> str | None:
    """Return a stop reason if recovery must terminate; else None."""
    if next_cycle > policy.max_recovery_cycles:
        return "max_recovery_cycles"
    started = recovery_started_at
    if started is None:
        state = load_recovery_state(run)
        raw = state.get("recovery_started_at")
        if raw:
            try:
                started = datetime.fromisoformat(str(raw))
            except ValueError:
                started = None
    if started is not None:
        elapsed = (_utc_now() - started).total_seconds()
        if elapsed > policy.max_recovery_duration_seconds:
            return "max_recovery_duration"
    if policy.max_cost is not None:
        cost = scene_analysis_cost_so_far(session, run.id)
        if cost > float(policy.max_cost):
            return "max_cost"
    return None


def begin_provider_recovery_pause(
    session: Session,
    run: AnalysisRun,
    exc: Exception,
    *,
    failed_scene: Scene | None,
    recovery_cycle: int,
    policy: ProviderRecoveryPolicy,
    recovery_started_at: datetime | None = None,
) -> dict[str, Any]:
    """Mark run as awaiting_provider_recovery and append an independent audit record."""
    progress = scene_analysis_progress(
        session, run, failed_scene_id=failed_scene.id if failed_scene else None
    )
    root_code = extract_provider_root_code(exc)
    detail_message = str(exc).strip() or root_code
    provider_exc = _exc_provider_error(exc)
    now = _utc_now()
    prior = load_recovery_state(run)
    started_at = recovery_started_at
    if started_at is None and prior.get("recovery_started_at"):
        try:
            started_at = datetime.fromisoformat(str(prior["recovery_started_at"]))
        except ValueError:
            started_at = None
    if started_at is None:
        started_at = now

    failed_invocation_id: int | None = None
    if isinstance(exc, StructuredOutputError):
        failed_invocation_id = exc.failed_invocation_id
    if not failed_invocation_id:
        latest = session.scalar(
            select(ModelInvocation)
            .where(
                ModelInvocation.run_id == run.id,
                ModelInvocation.task_type == "scene_analysis",
            )
            .order_by(ModelInvocation.id.desc())
        )
        failed_invocation_id = latest.id if latest else None

    last_failure = {
        "error_code": root_code,
        "root_error_code": root_code,
        "root_error_message": detail_message[:2000],
        "failed_stage": "scene_analysis",
        "exception_type": type(provider_exc or exc).__name__,
        "transport_kind": getattr(provider_exc, "transport_kind", None),
        "retryable": True,
        "failed_invocation_id": failed_invocation_id,
        "failed_scene_id": failed_scene.id if failed_scene else None,
        "failed_scene_index": failed_scene.ordinal if failed_scene else None,
        "completed_scene_count": progress.completed_scene_count,
        "remaining_scene_count": progress.remaining_scene_count,
        "total_scene_count": progress.total_scene_count,
        "provider_recovery_eligible": True,
    }

    cooldown_until = now.timestamp() + float(policy.circuit_cooldown_seconds)
    audit = {
        "kind": RECOVERY_AUDIT_KIND,
        "recovery_cycle": recovery_cycle,
        "recorded_at": now.isoformat(),
        "circuit_breaker": "open",
        "cooldown_seconds": policy.circuit_cooldown_seconds,
        "cooldown_until": datetime.fromtimestamp(cooldown_until, tz=timezone.utc).isoformat(),
        "root_error_code": root_code,
        "failed_scene_id": failed_scene.id if failed_scene else None,
        "failed_scene_index": failed_scene.ordinal if failed_scene else None,
        "failed_invocation_id": failed_invocation_id,
        "completed_scene_ids": list(progress.completed_scene_ids),
        "pending_scene_ids": list(progress.pending_scene_ids),
        "policy": {
            "max_recovery_cycles": policy.max_recovery_cycles,
            "max_recovery_duration_seconds": policy.max_recovery_duration_seconds,
            "max_cost": policy.max_cost,
            "circuit_cooldown_seconds": policy.circuit_cooldown_seconds,
        },
    }
    audits = list(prior.get("recovery_audits") or [])
    audits.append(audit)

    state: dict[str, Any] = {
        "kind": RECOVERY_PAUSE_KIND,
        "status": STATUS_AWAITING_PROVIDER_RECOVERY,
        "recovery_started_at": started_at.isoformat(),
        "recovery_cycles": recovery_cycle,
        "circuit_breaker": "open",
        "cooldown_seconds": policy.circuit_cooldown_seconds,
        "cooldown_until": audit["cooldown_until"],
        "root_error_code": root_code,
        "last_failure": last_failure,
        "recovery_audits": audits,
        "completed_scene_count": progress.completed_scene_count,
        "remaining_scene_count": progress.remaining_scene_count,
        "pending_scene_ids": list(progress.pending_scene_ids),
        "completed_scene_ids": list(progress.completed_scene_ids),
    }

    run.status = STATUS_AWAITING_PROVIDER_RECOVERY
    run.error_code = "SCENE_ANALYSIS_PROVIDER_RECOVERY"
    run.error_message = "Scene Analysis等待Provider恢复"
    run.root_error_code = root_code
    run.root_error_message = detail_message[:2000]
    run.failed_stage = "scene_analysis"
    run.retryable = True
    run.user_action_hint = (
        f"Provider传输中断；冷却 {policy.circuit_cooldown_seconds:.0f}s 后仅重试未完成Scene"
    )
    run.failed_invocation_id = failed_invocation_id
    run.completed_at = None
    _dump_state(run, state)
    return state


def resume_from_provider_recovery(run: AnalysisRun) -> dict[str, Any]:
    """Transition awaiting_provider_recovery → scene_analysis_running; keep audits."""
    state = load_recovery_state(run)
    state["kind"] = RECOVERY_STATE_KIND
    state["status"] = "scene_analysis_running"
    state["circuit_breaker"] = "half_open"
    state["resumed_at"] = _utc_now().isoformat()
    run.error_code = None
    run.error_message = None
    run.root_error_code = None
    run.root_error_message = None
    run.failed_stage = None
    run.failed_invocation_id = None
    run.retryable = False
    run.user_action_hint = None
    run.completed_at = None
    run.status = "scene_analysis_running"
    _dump_state(run, state)
    return state


def finalize_provider_recovery_exhausted(
    session: Session,
    run: AnalysisRun,
    exc: Exception,
    *,
    failed_scene: Scene | None,
    stop_reason: str,
    recovery_cycle: int,
    policy: ProviderRecoveryPolicy,
) -> None:
    """Terminal failure after recovery limits; preserve PROVIDER_REMOTE_DISCONNECT."""
    progress = scene_analysis_progress(
        session, run, failed_scene_id=failed_scene.id if failed_scene else None
    )
    root_code = extract_provider_root_code(exc) or "PROVIDER_REMOTE_DISCONNECT"
    detail_message = str(exc).strip() or root_code
    provider_exc = _exc_provider_error(exc)
    prior = load_recovery_state(run)
    now = _utc_now()

    failed_invocation_id: int | None = None
    if isinstance(exc, StructuredOutputError):
        failed_invocation_id = exc.failed_invocation_id
    if not failed_invocation_id:
        latest = session.scalar(
            select(ModelInvocation)
            .where(
                ModelInvocation.run_id == run.id,
                ModelInvocation.task_type == "scene_analysis",
            )
            .order_by(ModelInvocation.id.desc())
        )
        failed_invocation_id = latest.id if latest else None

    terminal_audit = {
        "kind": RECOVERY_AUDIT_KIND,
        "recovery_cycle": recovery_cycle,
        "recorded_at": now.isoformat(),
        "circuit_breaker": "open_terminal",
        "stop_reason": stop_reason,
        "root_error_code": root_code,
        "failed_scene_id": failed_scene.id if failed_scene else None,
        "terminal": True,
        "policy": {
            "max_recovery_cycles": policy.max_recovery_cycles,
            "max_recovery_duration_seconds": policy.max_recovery_duration_seconds,
            "max_cost": policy.max_cost,
        },
    }
    audits = list(prior.get("recovery_audits") or [])
    audits.append(terminal_audit)

    failure = {
        "error_code": root_code,
        "root_error_code": root_code,
        "root_error_message": detail_message[:2000],
        "failed_stage": "scene_analysis",
        "exception_type": type(provider_exc or exc).__name__,
        "transport_kind": getattr(provider_exc, "transport_kind", None),
        "retryable": False,
        "failed_invocation_id": failed_invocation_id,
        "failed_scene_id": failed_scene.id if failed_scene else None,
        "failed_scene_index": failed_scene.ordinal if failed_scene else None,
        "completed_scene_count": progress.completed_scene_count,
        "remaining_scene_count": progress.remaining_scene_count,
        "total_scene_count": progress.total_scene_count,
        "provider_recovery_exhausted": True,
        "provider_recovery_stop_reason": stop_reason,
        "recovery_cycles": recovery_cycle,
        "recovery_audits": audits,
    }

    run.error_code = "SCENE_ANALYSIS_FAILED"
    run.error_message = "Scene Analysis失败（Provider恢复超限）"
    run.root_error_code = root_code
    run.root_error_message = detail_message[:2000]
    run.failed_stage = "scene_analysis"
    run.retryable = False
    run.user_action_hint = (
        f"Provider恢复已终止（{stop_reason}）；已完成Scene保留，可人工排查后决定是否续跑"
    )
    run.failed_invocation_id = failed_invocation_id
    run.completed_at = now
    if progress.completed_scene_count > 0 and progress.remaining_scene_count > 0:
        run.status = "scene_analysis_partial"
    else:
        run.status = "failed"
    run.raw_output = json.dumps(
        {"kind": "scene_analysis_failure", **failure}, ensure_ascii=False
    )
    run.provider_health_at_failure = json.dumps(
        {"failure": failure, "provider_recovery": {"recovery_audits": audits}},
        ensure_ascii=False,
    )


def count_active_stage_reservations(session: Session, run_id: int, stage: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(CloudBudgetReservation)
            .where(
                CloudBudgetReservation.run_id == run_id,
                CloudBudgetReservation.stage == stage,
                CloudBudgetReservation.status == "active",
            )
        )
        or 0
    )


def clear_success_preserving_nothing(run: AnalysisRun) -> None:
    """Full success clear (no recovery blob needed)."""
    clear_scene_analysis_error_fields(run)
