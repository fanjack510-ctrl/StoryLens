"""MockRunRecoveryService contract (Phase 2A-P).

No silent auto-continue after restart. Resume requires explicit user/test action.
When Lab disabled: mark interrupted only; do not execute recovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode


CHECKPOINT_SCHEMA = "mock_whole_book_checkpoint"
CHECKPOINT_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class MockCheckpointRef:
    schema: str
    version: str
    stage_key: str | None
    attempt: int
    compatible: bool

    def __post_init__(self) -> None:
        if self.attempt < 0:
            raise ValueError("attempt must be >= 0")


@dataclass(frozen=True, slots=True)
class MockResumePlan:
    run_id: int
    resume_from_stage_key: str | None
    skip_completed_stages: tuple[str, ...]
    reset_downstream_stage_keys: tuple[str, ...]
    requires_explicit_resume: bool = True
    auto_execute_forbidden: bool = True

    def __post_init__(self) -> None:
        if not self.requires_explicit_resume or not self.auto_execute_forbidden:
            raise ValueError("recovery must require explicit resume; no silent auto-run")


@dataclass(frozen=True, slots=True)
class MockRecoveryDecision:
    run_id: int
    recoverable: bool
    reason_code: MockRunErrorCode | None
    marked_interrupted: bool
    resume_plan: MockResumePlan | None
    lab_enabled: bool


RECOVERY_PRECHECKS: tuple[str, ...] = (
    "run_is_mock_lab",
    "snapshot_exists",
    "snapshot_completed",
    "engine_id_version_compatible",
    "configuration_fingerprint_matches",
    "checkpoint_schema_version_compatible",
    "completed_stage_outputs_exist",
    "no_duplicate_asset_write",
    "no_canonical_overwrite",
    "lab_currently_enabled",
)


@runtime_checkable
class MockRunRecoveryService(Protocol):
    def scan_recoverable_runs(self) -> tuple[int, ...]: ...

    def mark_process_interrupted(self, run_id: int) -> MockRecoveryDecision: ...

    def validate_checkpoint(self, run_id: int) -> MockCheckpointRef: ...

    def build_resume_plan(self, run_id: int) -> MockResumePlan: ...

    def resume_recoverable_run(self, run_id: int) -> MockRecoveryDecision: ...

    def reject_unrecoverable_run(
        self, run_id: int, reason: MockRunErrorCode
    ) -> MockRecoveryDecision: ...


RECOVERY_PROTOCOL_METHODS: tuple[str, ...] = (
    "scan_recoverable_runs",
    "mark_process_interrupted",
    "validate_checkpoint",
    "build_resume_plan",
    "resume_recoverable_run",
    "reject_unrecoverable_run",
)


@dataclass(frozen=True, slots=True)
class RecoveryScanPolicy:
    on_startup_mark_interrupted: bool = True
    on_startup_auto_resume: bool = False
    require_lab_enabled_for_resume: bool = True
    require_explicit_user_or_test_resume: bool = True

    def __post_init__(self) -> None:
        if self.on_startup_auto_resume:
            raise ValueError("startup auto-resume is forbidden")
        if not self.require_explicit_user_or_test_resume:
            raise ValueError("explicit resume required")


DEFAULT_RECOVERY_SCAN_POLICY = RecoveryScanPolicy()


def decide_lab_disabled_recovery(run_id: int) -> MockRecoveryDecision:
    """When Lab is off: interrupt only; do not resume."""
    return MockRecoveryDecision(
        run_id=run_id,
        recoverable=False,
        reason_code=MockRunErrorCode.MOCK_LAB_DISABLED,
        marked_interrupted=True,
        resume_plan=None,
        lab_enabled=False,
    )


def engine_version_mismatch_decision(run_id: int) -> MockRecoveryDecision:
    return MockRecoveryDecision(
        run_id=run_id,
        recoverable=False,
        reason_code=MockRunErrorCode.MOCK_RUN_ENGINE_VERSION_MISMATCH,
        marked_interrupted=True,
        resume_plan=None,
        lab_enabled=True,
    )


COMPATIBLE_POST_INTERRUPT_STATUSES: frozenset[WholeBookRunViewStatus] = frozenset(
    {
        WholeBookRunViewStatus.INTERRUPTED,
        WholeBookRunViewStatus.PAUSED,
        WholeBookRunViewStatus.FAILED,
    }
)
