"""Partial result availability contract (Phase 2A-P).

Result API remains read-only and must not trigger runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PartialResultAvailability(StrEnum):
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class PartialResultGate:
    at_least_one_module_stage_completed: bool
    projection_status: PartialResultAvailability
    artifact_schema_valid: bool
    snapshot_consistent: bool
    mock: bool = True
    candidate: bool = True
    auto_canonical_forbidden: bool = True

    def __post_init__(self) -> None:
        if not self.auto_canonical_forbidden:
            raise ValueError("partial results must not auto-canonical")


def is_partial_result_readable(gate: PartialResultGate) -> bool:
    if gate.projection_status == PartialResultAvailability.UNAVAILABLE:
        return False
    return (
        gate.at_least_one_module_stage_completed
        and gate.artifact_schema_valid
        and gate.snapshot_consistent
    )


PARTIAL_RESULT_RULES: tuple[str, ...] = (
    "later_stage_failure_does_not_delete_existing_results",
    "partial_explicitly_marked",
    "mock_explicitly_marked",
    "candidate_explicitly_marked",
    "evidence_on_demand",
    "no_auto_canonical",
    "cancelled_run_candidates_still_readable",
    "interrupted_run_candidates_still_readable",
    "stale_and_failed_are_distinct",
    "result_api_does_not_trigger_run",
)
