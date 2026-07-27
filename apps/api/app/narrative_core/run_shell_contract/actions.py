"""Pause / Resume / Retry / Cancel action contracts (Phase 2A-P)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.run_state import can_resume, is_allowed_run_transition


class MockRunAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    RETRY = "retry"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class MockRunActionRequest:
    run_id: int
    action: MockRunAction
    operation_idempotency_key: str
    expected_state: WholeBookRunViewStatus | None = None
    expected_version: int | None = None
    stage_key: str | None = None
    confirm_cancel: bool = False

    def __post_init__(self) -> None:
        if not self.operation_idempotency_key.strip():
            raise ValueError("operation_idempotency_key required")
        if self.expected_state is None and self.expected_version is None:
            raise ValueError("expected_state or expected_version required")
        if self.action == MockRunAction.RETRY and not self.stage_key:
            raise ValueError("retry requires stage_key")
        if self.action == MockRunAction.CANCEL and not self.confirm_cancel:
            raise ValueError("cancel requires confirm_cancel")


@dataclass(frozen=True, slots=True)
class MockRunActionResult:
    run_id: int
    action: MockRunAction
    requested: bool
    accepted: bool
    current_state: WholeBookRunViewStatus
    idempotent_replay: bool = False
    detail_code: str | None = None


ACTION_RULES: dict[MockRunAction, tuple[str, ...]] = {
    MockRunAction.PAUSE: (
        "cooperative",
        "checkpoint_at_safe_point",
        "return_requested_accepted_current_state",
        "do_not_delete_results",
    ),
    MockRunAction.RESUME: (
        "from_paused_or_interrupted",
        "completed_stages_not_rerun",
        "restore_checkpoint",
        "same_run_id",
    ),
    MockRunAction.RETRY: (
        "failed_stage_only",
        "validate_downstream_impact",
        "reset_affected_downstream",
        "increment_attempt_count",
        "preserve_historical_artifacts",
        "new_artifact_new_attempt",
    ),
    MockRunAction.CANCEL: (
        "secondary_confirm",
        "cooperative",
        "stop_at_safe_point",
        "retain_completed_candidates",
        "cancelled_is_terminal",
        "do_not_delete_snapshot",
        "do_not_delete_book",
        "do_not_delete_user_files",
    ),
}


def action_allowed_for_state(
    action: MockRunAction, status: WholeBookRunViewStatus | str
) -> bool:
    status_value = WholeBookRunViewStatus(status)
    if action == MockRunAction.PAUSE:
        return is_allowed_run_transition(status_value, WholeBookRunViewStatus.PAUSED)
    if action == MockRunAction.RESUME:
        return can_resume(status_value)
    if action == MockRunAction.RETRY:
        return status_value == WholeBookRunViewStatus.FAILED
    if action == MockRunAction.CANCEL:
        return is_allowed_run_transition(status_value, WholeBookRunViewStatus.CANCELLED)
    return False
