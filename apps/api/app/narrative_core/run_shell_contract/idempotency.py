"""Idempotency and concurrency contract helpers (Phase 2A-P)."""

from __future__ import annotations

from dataclasses import dataclass

from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.run_state import (
    ACTIVE_RUN_STATUSES,
    FAILED_OCCUPIES_ACTIVE_SLOT_BY_DEFAULT,
    is_active_run_status,
)


@dataclass(frozen=True, slots=True)
class MockRunConcurrencyPolicy:
    max_active_mock_runs_per_book: int = 1
    failed_occupies_active_slot: bool = FAILED_OCCUPIES_ACTIVE_SLOT_BY_DEFAULT
    one_executor_per_run: bool = True
    create_uses_idempotency_key: bool = True
    operations_use_idempotency_key: bool = True
    state_updates_require_expected_state_or_version: bool = True
    duplicate_callbacks_must_not_duplicate_asset_versions: bool = True
    duplicate_stage_completion_must_not_duplicate_artifacts: bool = True
    restart_recovery_must_not_reinit_completed_stages: bool = True
    history_runs_allowed_for_same_book_snapshot_config: bool = True


DEFAULT_MOCK_RUN_CONCURRENCY_POLICY = MockRunConcurrencyPolicy()


def occupies_active_slot(
    status: WholeBookRunViewStatus | str,
    *,
    policy: MockRunConcurrencyPolicy = DEFAULT_MOCK_RUN_CONCURRENCY_POLICY,
) -> bool:
    status_value = WholeBookRunViewStatus(status)
    if status_value == WholeBookRunViewStatus.FAILED:
        return policy.failed_occupies_active_slot
    return is_active_run_status(status_value)


IDEMPOTENCY_RULES: tuple[str, ...] = (
    "create_uses_idempotency_key",
    "same_key_returns_same_run",
    "history_runs_allowed",
    "default_one_active_mock_run_per_book",
    "one_executor_per_run",
    "actions_use_operation_idempotency_key",
    "state_updates_use_expected_state_or_version",
    "no_duplicate_asset_version_on_replay",
    "no_duplicate_artifact_on_stage_complete_replay",
    "no_stage_reinit_on_recovery",
)

__all__ = [
    "ACTIVE_RUN_STATUSES",
    "DEFAULT_MOCK_RUN_CONCURRENCY_POLICY",
    "IDEMPOTENCY_RULES",
    "MockRunConcurrencyPolicy",
    "occupies_active_slot",
]
