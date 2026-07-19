"""Unified Analysis Recovery Center schemas (Phase 1D-C1-UAT-12)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RecoveryPauseReason = Literal[
    "provider_disconnected",
    "request_budget_insufficient",
    "token_budget_insufficient",
    "cost_budget_insufficient",
    "awaiting_reader_journey",
    "awaiting_provider_recovery",
    "credential_missing",
    "credential_unauthorized",
    "detection_checkpoint_pending",
    "scene_analysis_pending",
    "none",
]

ResumeStage = Literal[
    "none",
    "boundary_detection",
    "boundary_review",
    "scene_analysis",
    "reader_journey",
    "completed",
]

CheckStatus = Literal["pass", "fail", "warn", "skip"]


class RecoveryCheck(BaseModel):
    id: str
    label: str
    status: CheckStatus
    detail: str | None = None
    user_label: str | None = None
    internal_code: str | None = None
    required: float | int | None = None
    available: float | int | None = None
    shortfall: float | int | None = None


class RecoveryBlocker(BaseModel):
    code: str
    reason: RecoveryPauseReason | str
    user_message: str
    severity: Literal["block", "warn"] = "block"
    required: float | int | None = None
    available: float | int | None = None
    shortfall: float | int | None = None
    provider: str | None = None
    model: str | None = None
    settings_focus: Literal["api_key", "budget", "connection", "none"] | None = None


class RecoveryWarning(BaseModel):
    code: str
    message: str


class RecommendedAction(BaseModel):
    action: str
    label: str
    automatic: bool = False
    requires_user_authorization: bool = False


class BudgetAuthorizationProposal(BaseModel):
    scope: Literal["run_temporary", "global_permanent"] = "run_temporary"
    current_daily_request_limit: int
    current_remaining_requests: int
    required_requests: int
    suggested_extra_requests: int
    suggested_daily_request_limit: int | None = None
    estimated_cost: float = 0.0
    currency: str = "CNY"
    will_not_rerun: list[str] = Field(default_factory=list)
    message: str = ""


class RunBudgetAuthorizationRequest(BaseModel):
    scope: Literal["run_temporary", "global_permanent"] = "run_temporary"
    extra_requests: int = Field(ge=0, default=0)
    extra_tokens: int = Field(ge=0, default=0)
    extra_cost: float = Field(ge=0, default=0.0)
    # Only used when scope=global_permanent
    new_daily_request_limit: int | None = Field(default=None, ge=1)


class AnalysisRecoveryPlanResponse(BaseModel):
    run_id: int
    chapter_id: int | None = None
    status: str
    user_status: Literal["paused_recoverable", "running", "succeeded", "failed", "idle"]
    pause_reason: RecoveryPauseReason | str | None = None
    recoverable: bool
    blockers: list[RecoveryBlocker] = Field(default_factory=list)
    warnings: list[RecoveryWarning] = Field(default_factory=list)
    checks: list[RecoveryCheck] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    resume_stage: ResumeStage = "none"
    will_reuse_artifacts: list[str] = Field(default_factory=list)
    will_create_entities: list[str] = Field(default_factory=list)
    estimated_requests: int = 0
    estimated_tokens: int = 0
    estimated_cost: float = 0.0
    currency: str = "CNY"
    provider: str | None = None
    model: str | None = None
    request_hash: str | None = None
    recovery_attempts: int = 0
    budget_authorization_proposal: BudgetAuthorizationProposal | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    active_task: str | None = None
    duplicate_run_risk: bool = False
    existing_recovery_run_id: int | None = None
    reader_journey_run_id: int | None = None
    reader_journey_status: str | None = None
    current_stage: str | None = None
    retry_eligible: bool = False
    reservation_status: str | None = None


class AnalysisRecoverRequest(BaseModel):
    """Unified recover body.

    Legacy boundary checkpoint clients omit ``recovery_mode`` (treated as
    ``boundary_checkpoints``). The Recovery Center always sends ``unified``.
    """

    client_request_id: str = Field(min_length=8, max_length=64)
    cloud_consent: bool = False
    confirmed: bool = False
    provider_state_version: str | None = None
    recovery_mode: Literal["unified", "boundary_checkpoints"] | None = None
    authorize_budget: RunBudgetAuthorizationRequest | None = None
    # When False: apply safe fixes (reconnect / run auth) only; do not start model work.
    resume: bool = True


class AnalysisRecoverResponse(BaseModel):
    run_id: int
    status: str
    user_status: Literal["paused_recoverable", "running", "succeeded", "failed", "idle"]
    recoverable: bool
    idempotent_replay: bool = False
    actions_executed: list[str] = Field(default_factory=list)
    resume_stage: ResumeStage = "none"
    will_reuse_artifacts: list[str] = Field(default_factory=list)
    will_create_entities: list[str] = Field(default_factory=list)
    estimated_requests: int = 0
    estimated_tokens: int = 0
    estimated_cost: float = 0.0
    currency: str = "CNY"
    budget_authorization_proposal: BudgetAuthorizationProposal | None = None
    blockers: list[RecoveryBlocker] = Field(default_factory=list)
    warnings: list[RecoveryWarning] = Field(default_factory=list)
    checks: list[RecoveryCheck] = Field(default_factory=list)
    reader_journey_run_id: int | None = None
    created_analysis_run_id: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    http_request_sent: bool = False
    model_invocations_started: bool = False


class FullPipelineBudgetAdvisory(BaseModel):
    """Create-time full-pipeline budget advisory (pre-reservation)."""

    boundary_expected_requests: int = 0
    boundary_worst_requests: int = 0
    scene_analysis_expected_requests: int = 0
    scene_analysis_worst_requests: int = 0
    reader_journey_expected_requests: int = 0
    reader_journey_worst_requests: int = 0
    retry_repair_margin_requests: int = 0
    recovery_margin_requests: int = 0
    full_expected_requests: int = 0
    full_worst_requests: int = 0
    estimated_tokens: int = 0
    worst_case_tokens: int = 0
    estimated_cost: float = 0.0
    worst_case_cost: float = 0.0
    remaining_requests: int = 0
    remaining_tokens: int = 0
    remaining_cost: float = 0.0
    within_budget: bool = True
    exceeded_dimensions: list[str] = Field(default_factory=list)
    estimated_scene_count: int = 0
    message: str | None = None
