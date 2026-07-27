"""Mock Run state machine contract (Phase 2A-P).

Product statuses omit ``queued``. Frontend must not invent transitions.
All transitions require expected_state or expected_version and must be idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode

ACTIVE_RUN_STATUSES: frozenset[WholeBookRunViewStatus] = frozenset(
    {
        WholeBookRunViewStatus.PENDING,
        WholeBookRunViewStatus.RUNNING,
        WholeBookRunViewStatus.PAUSED,
        WholeBookRunViewStatus.INTERRUPTED,
    }
)

TERMINAL_RUN_STATUSES: frozenset[WholeBookRunViewStatus] = frozenset(
    {
        WholeBookRunViewStatus.COMPLETED,
        WholeBookRunViewStatus.CANCELLED,
    }
)

# failed does NOT occupy the active concurrency slot by default.
FAILED_OCCUPIES_ACTIVE_SLOT_BY_DEFAULT = False

ALLOWED_RUN_TRANSITIONS: dict[WholeBookRunViewStatus, frozenset[WholeBookRunViewStatus]] = {
    WholeBookRunViewStatus.PENDING: frozenset(
        {
            WholeBookRunViewStatus.RUNNING,
            WholeBookRunViewStatus.CANCELLED,
        }
    ),
    WholeBookRunViewStatus.RUNNING: frozenset(
        {
            WholeBookRunViewStatus.PAUSED,
            WholeBookRunViewStatus.INTERRUPTED,
            WholeBookRunViewStatus.COMPLETED,
            WholeBookRunViewStatus.FAILED,
            WholeBookRunViewStatus.CANCELLED,
        }
    ),
    WholeBookRunViewStatus.PAUSED: frozenset(
        {
            WholeBookRunViewStatus.RUNNING,
            WholeBookRunViewStatus.CANCELLED,
        }
    ),
    WholeBookRunViewStatus.INTERRUPTED: frozenset(
        {
            WholeBookRunViewStatus.RUNNING,
            WholeBookRunViewStatus.CANCELLED,
            WholeBookRunViewStatus.FAILED,
        }
    ),
    WholeBookRunViewStatus.FAILED: frozenset(
        {
            WholeBookRunViewStatus.RUNNING,  # retry / resume policy only
            WholeBookRunViewStatus.CANCELLED,
        }
    ),
    WholeBookRunViewStatus.COMPLETED: frozenset(),
    WholeBookRunViewStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class RunStateTransitionRequest:
    run_id: int
    from_state: WholeBookRunViewStatus
    to_state: WholeBookRunViewStatus
    expected_state: WholeBookRunViewStatus | None = None
    expected_version: int | None = None
    actor: str = "system"
    operation_idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if self.expected_state is None and self.expected_version is None:
            raise ValueError("expected_state or expected_version required")


@dataclass(frozen=True, slots=True)
class RunStateTransitionResult:
    run_id: int
    previous_state: WholeBookRunViewStatus
    new_state: WholeBookRunViewStatus
    applied: bool
    idempotent_replay: bool
    version: int
    error_code: MockRunErrorCode | None = None


def is_allowed_run_transition(
    current: WholeBookRunViewStatus | str,
    target: WholeBookRunViewStatus | str,
) -> bool:
    current_status = WholeBookRunViewStatus(current)
    target_status = WholeBookRunViewStatus(target)
    if current_status == target_status:
        return True  # idempotent no-op
    return target_status in ALLOWED_RUN_TRANSITIONS.get(current_status, frozenset())


def is_active_run_status(status: WholeBookRunViewStatus | str) -> bool:
    return WholeBookRunViewStatus(status) in ACTIVE_RUN_STATUSES


def is_terminal_run_status(status: WholeBookRunViewStatus | str) -> bool:
    return WholeBookRunViewStatus(status) in TERMINAL_RUN_STATUSES


def can_resume(status: WholeBookRunViewStatus | str) -> bool:
    """Resume from paused/interrupted only. failed uses retry policy."""
    status_value = WholeBookRunViewStatus(status)
    if status_value in TERMINAL_RUN_STATUSES:
        return False
    return status_value in {
        WholeBookRunViewStatus.PAUSED,
        WholeBookRunViewStatus.INTERRUPTED,
    }


def validate_transition_or_raise(
    current: WholeBookRunViewStatus | str,
    target: WholeBookRunViewStatus | str,
) -> None:
    if not is_allowed_run_transition(current, target):
        raise ValueError(
            f"illegal run transition {WholeBookRunViewStatus(current).value} "
            f"-> {WholeBookRunViewStatus(target).value}"
        )
