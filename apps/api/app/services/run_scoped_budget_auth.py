"""Run-scoped temporary budget authorization (no global settings mutation)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun
from app.services.staged_budget import BudgetAmounts

RUN_BUDGET_AUTH_KIND = "run_scoped_budget_authorization"
UNIFIED_RECOVER_MARKER_KIND = "unified_analysis_recover"
# Alias preferred by V1.0 product copy / audit trails.
RUN_TEMPORARY_REQUEST_ALLOWANCE = "run_temporary_request_allowance"


def _parse_raw(run: AnalysisRun) -> dict[str, Any]:
    if not run.raw_output:
        return {}
    try:
        payload = json.loads(run.raw_output)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _dump_raw(run: AnalysisRun, payload: dict[str, Any]) -> None:
    run.raw_output = json.dumps(payload, ensure_ascii=False, sort_keys=True)


def load_run_budget_auth(run: AnalysisRun) -> dict[str, Any] | None:
    payload = _parse_raw(run)
    auth = payload.get(RUN_BUDGET_AUTH_KIND)
    if isinstance(auth, dict) and auth.get("scope") == "run_temporary":
        return auth
    return None


def apply_run_budget_auth(
    run: AnalysisRun,
    *,
    extra_requests: int,
    extra_tokens: int = 0,
    extra_cost: float = 0.0,
    client_request_id: str,
) -> dict[str, Any]:
    """Idempotently store/merge temporary run authorization on AnalysisRun.raw_output."""
    payload = _parse_raw(run)
    existing = payload.get(RUN_BUDGET_AUTH_KIND)
    if (
        isinstance(existing, dict)
        and existing.get("client_request_id") == client_request_id
        and int(existing.get("extra_requests") or 0) >= int(extra_requests)
    ):
        return existing
    prior_extra_req = int(existing.get("extra_requests") or 0) if isinstance(existing, dict) else 0
    prior_extra_tok = int(existing.get("extra_tokens") or 0) if isinstance(existing, dict) else 0
    prior_extra_cost = float(existing.get("extra_cost") or 0) if isinstance(existing, dict) else 0.0
    auth = {
        "kind": RUN_BUDGET_AUTH_KIND,
        "scope": "run_temporary",
        "allowance_kind": RUN_TEMPORARY_REQUEST_ALLOWANCE,
        "extra_requests": max(prior_extra_req, int(extra_requests)),
        "extra_tokens": max(prior_extra_tok, int(extra_tokens)),
        "extra_cost": max(prior_extra_cost, float(extra_cost)),
        "client_request_id": client_request_id,
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "mutates_daily_request_limit": False,
    }
    payload[RUN_BUDGET_AUTH_KIND] = auth
    payload[RUN_TEMPORARY_REQUEST_ALLOWANCE] = {
        "extra_requests": auth["extra_requests"],
        "scope": "run_temporary",
        "client_request_id": client_request_id,
        "authorized_at": auth["authorized_at"],
    }
    _dump_raw(run, payload)
    return auth


def effective_remaining_with_run_auth(
    run: AnalysisRun | None, remaining: BudgetAmounts
) -> BudgetAmounts:
    if run is None:
        return remaining
    auth = load_run_budget_auth(run)
    if not auth:
        return remaining
    return BudgetAmounts(
        remaining.requests + int(auth.get("extra_requests") or 0),
        remaining.tokens + int(auth.get("extra_tokens") or 0),
        round(remaining.estimated_cost + float(auth.get("extra_cost") or 0), 6),
    )


def inflate_daily_limit_for_run(run: AnalysisRun | None, daily_limit: int) -> int:
    if run is None:
        return daily_limit
    auth = load_run_budget_auth(run)
    if not auth:
        return daily_limit
    return int(daily_limit) + int(auth.get("extra_requests") or 0)


def apply_run_auth_to_usage(
    run: AnalysisRun | None,
    usage: dict[str, Any],
    budget: dict[str, Any],
) -> dict[str, Any]:
    """Inflate request (and optional token/cost) remaining for one Run only.

    Does not mutate ApplicationSetting.cloud_daily_request_limit.
    Cost ceiling still respects user daily cost limit unless extra_cost > 0
    was explicitly authorized on the Run.
    """
    if run is None:
        return usage
    auth = load_run_budget_auth(run)
    if not auth:
        return usage
    extra_req = int(auth.get("extra_requests") or 0)
    extra_tok = int(auth.get("extra_tokens") or 0)
    extra_cost = float(auth.get("extra_cost") or 0.0)
    if extra_req <= 0 and extra_tok <= 0 and extra_cost <= 0:
        return usage
    out = dict(usage)
    out["remaining_requests"] = int(usage.get("remaining_requests") or 0) + extra_req
    out["available_requests"] = int(usage.get("available_requests") or 0) + extra_req
    out["remaining_tokens"] = int(usage.get("remaining_tokens") or 0) + extra_tok
    out["available_tokens"] = int(usage.get("available_tokens") or 0) + extra_tok
    out["remaining_estimated_cost"] = round(
        float(usage.get("remaining_estimated_cost") or 0) + extra_cost, 6
    )
    out["available_estimated_cost"] = round(
        float(usage.get("available_estimated_cost") or 0) + extra_cost, 6
    )
    out["run_temporary_extra_requests"] = extra_req
    out["effective_daily_request_limit"] = inflate_daily_limit_for_run(
        run, int(budget.get("cloud_daily_request_limit") or 0)
    )
    out[RUN_TEMPORARY_REQUEST_ALLOWANCE] = {
        "extra_requests": extra_req,
        "extra_tokens": extra_tok,
        "extra_cost": extra_cost,
        "scope": "run_temporary",
    }
    # Re-evaluate request-dimension gate with inflated ceiling; keep cost/token
    # hard stops unless explicitly authorized extras cover them.
    from app.services.cloud_budget import cloud_block_reasons

    effective_budget = dict(budget)
    effective_budget["cloud_daily_request_limit"] = out["effective_daily_request_limit"]
    if extra_tok > 0:
        effective_budget["cloud_daily_token_limit"] = int(
            budget.get("cloud_daily_token_limit") or 0
        ) + extra_tok
    if extra_cost > 0:
        effective_budget["cloud_daily_estimated_cost_limit"] = round(
            float(budget.get("cloud_daily_estimated_cost_limit") or 0) + extra_cost, 6
        )
    # Pricing dict is not needed for limit arithmetic; callers already gated pricing.
    pricing = {"enabled": True}
    reasons = cloud_block_reasons(
        cloud_enabled=True,
        budget=effective_budget,
        pricing=pricing,
        requests=int(usage.get("request_count") or 0),
        tokens=int(usage.get("total_tokens") or 0),
        cost=float(usage.get("estimated_cost") or 0),
    )
    # Preserve master-switch / protection flags from original usage when present.
    original_reasons = list(usage.get("blocked_reasons") or [])
    non_request = [
        r
        for r in original_reasons
        if "请求" not in str(r) and "Token" not in str(r) and "费用" not in str(r)
    ]
    out["blocked_reasons"] = non_request + reasons
    out["within_budget"] = not out["blocked_reasons"]
    return out


def load_unified_recover_marker(run: AnalysisRun) -> dict[str, Any] | None:
    payload = _parse_raw(run)
    marker = payload.get(UNIFIED_RECOVER_MARKER_KIND)
    return marker if isinstance(marker, dict) else None


def store_unified_recover_marker(
    run: AnalysisRun,
    *,
    client_request_id: str,
    actions: list[str],
    resume_stage: str,
    recovery_attempts: int,
    manual_recovery_attempts: int | None = None,
    auto_recovery_attempts: int | None = None,
    last_recovery_kind: str | None = None,
    last_recovery_reason: str | None = None,
) -> dict[str, Any]:
    payload = _parse_raw(run)
    prior = payload.get(UNIFIED_RECOVER_MARKER_KIND)
    prior = prior if isinstance(prior, dict) else {}
    marker = {
        "kind": UNIFIED_RECOVER_MARKER_KIND,
        "client_request_id": client_request_id,
        "actions": list(actions),
        "resume_stage": resume_stage,
        "recovery_attempts": recovery_attempts,
        "manual_recovery_attempts": (
            int(manual_recovery_attempts)
            if manual_recovery_attempts is not None
            else int(prior.get("manual_recovery_attempts") or recovery_attempts or 0)
        ),
        "auto_recovery_attempts": (
            int(auto_recovery_attempts)
            if auto_recovery_attempts is not None
            else int(prior.get("auto_recovery_attempts") or 0)
        ),
        "last_recovery_kind": last_recovery_kind or prior.get("last_recovery_kind"),
        "last_recovery_reason": last_recovery_reason or prior.get("last_recovery_reason"),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    payload[UNIFIED_RECOVER_MARKER_KIND] = marker
    _dump_raw(run, payload)
    return marker


def get_run_for_budget(session: Session, run_id: int | None) -> AnalysisRun | None:
    if run_id is None:
        return None
    return session.get(AnalysisRun, run_id)
