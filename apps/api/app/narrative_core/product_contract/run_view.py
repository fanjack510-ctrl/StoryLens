"""Run view + stage progress contracts (Phase 1D-P).

allowed_actions are authoritative from backend; frontend must not invent them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.narrative_core.enums import StageStatus, WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.product_contract.enums import (
    RunAllowedAction,
    WholeBookModuleStatus,
    WholeBookRunViewStatus,
)


@dataclass(frozen=True, slots=True)
class WholeBookStageProgressDto:
    stage_key: str
    display_name: str
    order: int
    status: StageStatus
    required: bool
    resumable: bool
    retryable: bool
    progress_percent: float | None
    started_at: str | None
    completed_at: str | None
    attempt_count: int
    checkpoint_available: bool
    token_input: int | None
    token_output: int | None
    cost: float | None
    output_artifact_ids: tuple[str, ...]
    produced_module_keys: tuple[str, ...]
    warnings: tuple[str, ...]
    error_code: str | None
    error_message: str | None
    allowed_actions: tuple[RunAllowedAction, ...]

    def __post_init__(self) -> None:
        if self.error_message and len(self.error_message) > 500:
            raise ValueError("error_message must not contain full novel body")
        if self.progress_percent is not None and not (0.0 <= self.progress_percent <= 100.0):
            raise ValueError("progress_percent out of range")


@dataclass(frozen=True, slots=True)
class WholeBookRunViewState:
    run_id: int
    book_id: int
    snapshot_id: int
    analysis_mode: WholeBookAnalysisMode
    status: WholeBookRunViewStatus
    current_stage: str | None
    stages: tuple[WholeBookStageProgressDto, ...]
    completed_modules: tuple[WholeBookModuleKey, ...]
    available_modules: tuple[WholeBookModuleKey, ...]
    failed_modules: tuple[WholeBookModuleKey, ...]
    partial_results_available: bool
    progress_percent: float | None
    token_usage: dict[str, int] = field(default_factory=dict)
    cost: float | None = None
    started_at: str | None = None
    updated_at: str | None = None
    estimated_remaining: str | None = None
    blocking_issue: str | None = None
    allowed_actions: tuple[RunAllowedAction, ...] = ()
    module_statuses: dict[str, WholeBookModuleStatus] = field(default_factory=dict)


# Transition matrix (product contract; services enforce at implementation time).
RUN_ACTION_RULES: dict[RunAllowedAction, frozenset[WholeBookRunViewStatus]] = {
    RunAllowedAction.PAUSE: frozenset({WholeBookRunViewStatus.RUNNING}),
    RunAllowedAction.RESUME: frozenset(
        {WholeBookRunViewStatus.PAUSED, WholeBookRunViewStatus.INTERRUPTED}
    ),
    RunAllowedAction.RETRY: frozenset({WholeBookRunViewStatus.FAILED}),
    RunAllowedAction.CANCEL: frozenset(
        {
            WholeBookRunViewStatus.PENDING,
            WholeBookRunViewStatus.RUNNING,
            WholeBookRunViewStatus.PAUSED,
            WholeBookRunViewStatus.INTERRUPTED,
        }
    ),
    RunAllowedAction.VIEW_PARTIAL_RESULTS: frozenset(
        {
            WholeBookRunViewStatus.RUNNING,
            WholeBookRunViewStatus.PAUSED,
            WholeBookRunViewStatus.INTERRUPTED,
            WholeBookRunViewStatus.COMPLETED,
            WholeBookRunViewStatus.FAILED,
            WholeBookRunViewStatus.CANCELLED,
        }
    ),
}


def is_action_allowed_for_status(
    action: RunAllowedAction,
    status: WholeBookRunViewStatus,
) -> bool:
    return status in RUN_ACTION_RULES.get(action, frozenset())
