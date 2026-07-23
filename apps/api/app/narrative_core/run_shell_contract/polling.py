"""MockRunPollingPolicy contract (Phase 2A-P).

No WebSocket. No 100ms high-frequency polling. Network errors must not mark Run failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.narrative_core.product_contract.enums import WholeBookRunViewStatus


class PollingBackoffPolicy(StrEnum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class MockRunPollingPolicy:
    initial_interval_ms: int
    running_interval_ms: int
    paused_interval_ms: int
    terminal_stop: bool
    max_consecutive_errors: int
    backoff_policy: PollingBackoffPolicy
    hidden_page_interval_ms: int = 10_000
    min_interval_ms: int = 1000
    websocket_forbidden: bool = True

    def __post_init__(self) -> None:
        if self.initial_interval_ms < self.min_interval_ms:
            raise ValueError("initial_interval_ms below safety floor")
        if self.running_interval_ms < self.min_interval_ms:
            raise ValueError("running_interval_ms below safety floor (no 100ms polling)")
        if self.paused_interval_ms < self.running_interval_ms:
            raise ValueError("paused_interval_ms should be >= running_interval_ms")
        if self.max_consecutive_errors < 1:
            raise ValueError("max_consecutive_errors must be >= 1")
        if not self.terminal_stop:
            raise ValueError("terminal_stop must be true")
        if not self.websocket_forbidden:
            raise ValueError("WebSocket polling is forbidden in Phase 2A")


DEFAULT_MOCK_RUN_POLLING_POLICY = MockRunPollingPolicy(
    initial_interval_ms=1500,
    running_interval_ms=1500,
    paused_interval_ms=4000,
    terminal_stop=True,
    max_consecutive_errors=5,
    backoff_policy=PollingBackoffPolicy.EXPONENTIAL,
    hidden_page_interval_ms=10_000,
)


def interval_for_status(
    policy: MockRunPollingPolicy,
    status: WholeBookRunViewStatus | str,
    *,
    page_visible: bool = True,
) -> int | None:
    status_value = WholeBookRunViewStatus(status)
    if status_value in {
        WholeBookRunViewStatus.COMPLETED,
        WholeBookRunViewStatus.FAILED,
        WholeBookRunViewStatus.CANCELLED,
    }:
        return None if policy.terminal_stop else policy.paused_interval_ms
    if status_value in {
        WholeBookRunViewStatus.PAUSED,
        WholeBookRunViewStatus.INTERRUPTED,
    }:
        base = policy.paused_interval_ms
    elif status_value == WholeBookRunViewStatus.RUNNING:
        base = policy.running_interval_ms
    else:
        base = policy.initial_interval_ms
    if not page_visible:
        return max(base, policy.hidden_page_interval_ms)
    return base


POLLING_RULES: tuple[str, ...] = (
    "no_sub_1000ms_polling",
    "reduce_frequency_when_hidden",
    "backoff_on_consecutive_errors",
    "stop_on_terminal",
    "cancel_old_poll_on_run_switch",
    "cancel_poll_on_app_exit",
    "discard_stale_responses_by_updated_at_or_version",
    "network_error_must_not_mark_run_failed",
    "frontend_close_must_not_cancel_backend_run",
    "no_websocket",
)
