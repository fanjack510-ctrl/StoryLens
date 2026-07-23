"""Frozen AnalysisRunStage status transition matrix (Phase 1P).

Agent B must implement this matrix and must not extend it without a new Change.
"""

from __future__ import annotations

from app.narrative_core.enums import StageStatus

# Terminal statuses: no outgoing transitions under normal rules.
_TERMINAL: frozenset[StageStatus] = frozenset(
    {
        StageStatus.COMPLETED,
        StageStatus.SKIPPED,
        StageStatus.CANCELLED,
    }
)

ALLOWED_STAGE_TRANSITIONS: dict[StageStatus, frozenset[StageStatus]] = {
    StageStatus.PENDING: frozenset(
        {
            StageStatus.RUNNING,
            StageStatus.SKIPPED,
            StageStatus.CANCELLED,
        }
    ),
    StageStatus.RUNNING: frozenset(
        {
            StageStatus.COMPLETED,
            StageStatus.FAILED,
            StageStatus.PAUSED,
            StageStatus.INTERRUPTED,
            StageStatus.CANCELLED,
        }
    ),
    StageStatus.PAUSED: frozenset(
        {
            StageStatus.RUNNING,
            StageStatus.CANCELLED,
        }
    ),
    StageStatus.INTERRUPTED: frozenset(
        {
            StageStatus.RUNNING,
            StageStatus.FAILED,
            StageStatus.CANCELLED,
        }
    ),
    StageStatus.FAILED: frozenset(
        {
            StageStatus.RUNNING,  # retry failed stage; must bump attempt_count
            StageStatus.CANCELLED,
        }
    ),
    StageStatus.COMPLETED: frozenset(),  # terminal; cannot re-enter running
    StageStatus.SKIPPED: frozenset(),
    StageStatus.CANCELLED: frozenset(),
}


def is_allowed_stage_transition(current: StageStatus | str, target: StageStatus | str) -> bool:
    current_status = StageStatus(current)
    target_status = StageStatus(target)
    return target_status in ALLOWED_STAGE_TRANSITIONS.get(current_status, frozenset())


def is_terminal_stage_status(status: StageStatus | str) -> bool:
    return StageStatus(status) in _TERMINAL
