"""Stage lifecycle rules for Mock Whole-Book runs (Phase 2A-P).

Reuses Phase 1A stage transitions + Phase 1C 10-stage catalog.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.narrative_core.enums import WholeBookStageKey
from app.narrative_core.stage_transitions import (
    ALLOWED_STAGE_TRANSITIONS,
    is_allowed_stage_transition,
    is_terminal_stage_status,
)

ORDERED_MOCK_STAGE_KEYS: tuple[WholeBookStageKey, ...] = (
    WholeBookStageKey.BUILD_FULLTEXT_INDEX,
    WholeBookStageKey.RESOLVE_ENTITIES,
    WholeBookStageKey.ANALYZE_STRUCTURE,
    WholeBookStageKey.ANALYZE_STORYLINES,
    WholeBookStageKey.ANALYZE_CHARACTERS,
    WholeBookStageKey.ANALYZE_HOOKS,
    WholeBookStageKey.ANALYZE_CAUSALITY_TIMELINE,
    WholeBookStageKey.GENERATE_DIAGNOSTICS,
    WholeBookStageKey.VERIFY_EVIDENCE,
    WholeBookStageKey.PERSIST_NARRATIVE_ASSETS,
)

STAGE_LIFECYCLE_RULES: tuple[str, ...] = (
    "execute_in_dependency_order",
    "completed_stages_do_not_rerun",
    "skipped_stages_require_reason",
    "paused_saves_checkpoint",
    "interrupted_saves_last_checkpoint",
    "retry_increments_attempt_count",
    "failed_retry_resets_affected_downstream_only",
    "cancel_checked_before_and_after_stage",
    "budget_guard_before_writes",
    "write_whole_book_stage_artifact_envelope",
    "artifact_marked_mock_synthetic_non_production",
    "stage_output_creates_candidates_only",
    "no_auto_confirm",
    "no_auto_lock",
    "no_canonical_overwrite",
)


@dataclass(frozen=True, slots=True)
class StageRetryImpact:
    failed_stage_key: str
    reset_downstream_stage_keys: tuple[str, ...]
    preserve_completed_upstream: bool = True
    preserve_historical_artifacts: bool = True
    new_attempt_for_new_artifact: bool = True

    def __post_init__(self) -> None:
        if self.failed_stage_key in self.reset_downstream_stage_keys:
            raise ValueError("failed stage is retried, not listed as downstream reset alone")


def downstream_stage_keys(stage_key: str) -> tuple[str, ...]:
    keys = [k.value for k in ORDERED_MOCK_STAGE_KEYS]
    if stage_key not in keys:
        raise ValueError(f"unknown stage_key: {stage_key}")
    idx = keys.index(stage_key)
    return tuple(keys[idx + 1 :])


def build_stage_retry_impact(failed_stage_key: str) -> StageRetryImpact:
    return StageRetryImpact(
        failed_stage_key=failed_stage_key,
        reset_downstream_stage_keys=downstream_stage_keys(failed_stage_key),
    )


__all__ = [
    "ALLOWED_STAGE_TRANSITIONS",
    "ORDERED_MOCK_STAGE_KEYS",
    "STAGE_LIFECYCLE_RULES",
    "StageRetryImpact",
    "build_stage_retry_impact",
    "downstream_stage_keys",
    "is_allowed_stage_transition",
    "is_terminal_stage_status",
]
