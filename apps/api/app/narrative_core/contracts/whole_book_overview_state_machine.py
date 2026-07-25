"""Frozen Whole-Book Overview Run / Stage / Window transition validators (STEP 2.1).

Does not replace Free AnalysisRunStage transitions in stage_transitions.py.
Overview production uses OverviewProductionStageKey + this matrix.
"""

from __future__ import annotations

from app.narrative_core.enums import (
    OverviewProductionStageKey,
    RunStatus,
    StageStatus,
    WindowStatus,
)

# ---------------------------------------------------------------------------
# Run transitions (native Overview production)
# ---------------------------------------------------------------------------

ALLOWED_OVERVIEW_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset(
        {
            RunStatus.PREPARING,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.PREPARING: frozenset(
        {
            RunStatus.ANALYZING,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.ANALYZING: frozenset(
        {
            RunStatus.MATERIALIZING,
            RunStatus.FAILED,
            RunStatus.PAUSED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.MATERIALIZING: frozenset(
        {
            RunStatus.ANALYZING,
            RunStatus.SYNTHESIZING,
            RunStatus.FAILED,
            RunStatus.PAUSED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.SYNTHESIZING: frozenset(
        {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.PAUSED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.PAUSED: frozenset(
        {
            RunStatus.ANALYZING,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.FAILED: frozenset(
        {
            RunStatus.PREPARING,
            RunStatus.ANALYZING,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    # Legacy Free values — not part of Overview production path, but listed
    # so validators can deny misuse without KeyError.
    RunStatus.QUEUED: frozenset({RunStatus.CANCELLED, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset({RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.PAUSED}),
    RunStatus.INTERRUPTED: frozenset({RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.ANALYZING}),
}

# ---------------------------------------------------------------------------
# Overview production stage transitions (subset of StageStatus)
# ---------------------------------------------------------------------------

ALLOWED_OVERVIEW_STAGE_TRANSITIONS: dict[StageStatus, frozenset[StageStatus]] = {
    StageStatus.PENDING: frozenset({StageStatus.RUNNING, StageStatus.SKIPPED}),
    StageStatus.RUNNING: frozenset(
        {StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.SKIPPED}
    ),
    StageStatus.FAILED: frozenset({StageStatus.RUNNING}),  # retry
    StageStatus.COMPLETED: frozenset(),
    StageStatus.SKIPPED: frozenset(),
}

OVERVIEW_PRODUCTION_STAGE_ORDER: tuple[OverviewProductionStageKey, ...] = (
    OverviewProductionStageKey.SNAPSHOT_PREFLIGHT,
    OverviewProductionStageKey.BUILD_CONTEXT_WINDOWS,
    OverviewProductionStageKey.EXTRACT_OVERVIEW_FACTS,
    OverviewProductionStageKey.MATERIALIZE_ASSETS,
    OverviewProductionStageKey.GENERATE_OVERVIEW_PROJECTION,
    OverviewProductionStageKey.FINALIZE,
)

# ---------------------------------------------------------------------------
# Window transitions
# ---------------------------------------------------------------------------

ALLOWED_WINDOW_TRANSITIONS: dict[WindowStatus, frozenset[WindowStatus]] = {
    WindowStatus.PENDING: frozenset(
        {WindowStatus.RUNNING, WindowStatus.SKIPPED, WindowStatus.FAILED}
    ),
    WindowStatus.RUNNING: frozenset(
        {WindowStatus.COMPLETED, WindowStatus.FAILED, WindowStatus.SKIPPED}
    ),
    WindowStatus.FAILED: frozenset({WindowStatus.RUNNING}),  # retry
    WindowStatus.COMPLETED: frozenset(),
    WindowStatus.SKIPPED: frozenset(),
}


def _as_run_status(value: RunStatus | str) -> RunStatus:
    return value if isinstance(value, RunStatus) else RunStatus(value)


def _as_stage_status(value: StageStatus | str) -> StageStatus:
    return value if isinstance(value, StageStatus) else StageStatus(value)


def _as_window_status(value: WindowStatus | str) -> WindowStatus:
    return value if isinstance(value, WindowStatus) else WindowStatus(value)


def is_allowed_overview_run_transition(
    current: RunStatus | str, target: RunStatus | str
) -> bool:
    current_status = _as_run_status(current)
    target_status = _as_run_status(target)
    return target_status in ALLOWED_OVERVIEW_RUN_TRANSITIONS.get(current_status, frozenset())


def validate_overview_run_transition(current: RunStatus | str, target: RunStatus | str) -> None:
    if not is_allowed_overview_run_transition(current, target):
        raise ValueError(
            f"invalid overview run transition: {_as_run_status(current).value} -> "
            f"{_as_run_status(target).value}"
        )


def is_allowed_overview_stage_transition(
    current: StageStatus | str, target: StageStatus | str
) -> bool:
    current_status = _as_stage_status(current)
    target_status = _as_stage_status(target)
    return target_status in ALLOWED_OVERVIEW_STAGE_TRANSITIONS.get(current_status, frozenset())


def validate_overview_stage_transition(
    current: StageStatus | str, target: StageStatus | str
) -> None:
    if not is_allowed_overview_stage_transition(current, target):
        raise ValueError(
            f"invalid overview stage transition: {_as_stage_status(current).value} -> "
            f"{_as_stage_status(target).value}"
        )


def is_allowed_window_transition(
    current: WindowStatus | str, target: WindowStatus | str
) -> bool:
    current_status = _as_window_status(current)
    target_status = _as_window_status(target)
    return target_status in ALLOWED_WINDOW_TRANSITIONS.get(current_status, frozenset())


def validate_window_transition(current: WindowStatus | str, target: WindowStatus | str) -> None:
    if not is_allowed_window_transition(current, target):
        raise ValueError(
            f"invalid window transition: {_as_window_status(current).value} -> "
            f"{_as_window_status(target).value}"
        )


def is_overview_production_stage_key(stage_key: str | OverviewProductionStageKey) -> bool:
    try:
        OverviewProductionStageKey(str(stage_key))
    except ValueError:
        return False
    return True
