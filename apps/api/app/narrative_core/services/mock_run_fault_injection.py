"""Mock Run fault injection profiles (Phase 2A Agent O).

Test/dev only. Forbidden in production. Deterministic. No model calls.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from app.narrative_core.enums import WholeBookStageKey
from app.narrative_core.services.mock_whole_book_engine import MOCK_ENGINE_ID, MOCK_ENGINE_VERSION


class FaultInjectionKind(StrEnum):
    FAIL_AT_STAGE = "fail_at_stage"
    INTERRUPT_AT_STAGE = "interrupt_at_stage"
    PAUSE_AT_STAGE = "pause_at_stage"
    BUDGET_DENIED_AT_STAGE = "budget_denied_at_stage"
    CORRUPTED_CHECKPOINT = "corrupted_checkpoint"
    ENGINE_VERSION_MISMATCH = "engine_version_mismatch"
    DUPLICATE_STAGE_COMPLETION = "duplicate_stage_completion"
    DUPLICATE_ASSET_WRITE = "duplicate_asset_write"
    TASK_REGISTRY_LOSS = "task_registry_loss"
    PROCESS_RESTART_MARKER = "process_restart_marker"


FORBIDDEN_PRODUCTION_ENVS: frozenset[str] = frozenset(
    {"production", "prod", "release", "staging"}
)


def assert_fault_injection_allowed(*, environment: str | None = None) -> None:
    env = (environment or os.getenv("STORYLENS_APP_ENV") or os.getenv("APP_ENV") or "test").lower()
    if env in FORBIDDEN_PRODUCTION_ENVS:
        raise RuntimeError("fault injection is forbidden in production environments")
    if os.getenv("STORYLENS_PRODUCTION", "").strip() in {"1", "true", "True"}:
        raise RuntimeError("fault injection is forbidden when STORYLENS_PRODUCTION is set")


@dataclass(frozen=True, slots=True)
class MockFaultInjectionProfile:
    """Lab/test-only deterministic fault profile. Never written to formal config."""

    kind: FaultInjectionKind | None = None
    stage_key: str | None = None
    engine_id: str = MOCK_ENGINE_ID
    engine_version: str = MOCK_ENGINE_VERSION
    mismatched_engine_version: str = "9.9.9-mismatch"
    corrupt_checkpoint_blob: str = "{not-json"
    process_restart_marker: str | None = None
    duplicate_count: int = 2
    enabled: bool = True
    non_production: bool = True
    test_or_dev_only: bool = True
    deterministic: bool = True
    calls_model: bool = False
    writes_formal_config: bool = False
    pollutes_real_book_data: bool = False

    def __post_init__(self) -> None:
        if not self.non_production or not self.test_or_dev_only:
            raise ValueError("fault injection must be non_production test/dev only")
        if self.calls_model or self.writes_formal_config or self.pollutes_real_book_data:
            raise ValueError("fault injection must not call models or pollute real data")
        if not self.deterministic:
            raise ValueError("fault injection must be deterministic")
        if self.duplicate_count < 2:
            raise ValueError("duplicate_count must be >= 2")

    def fingerprint(self) -> str:
        payload = {
            "kind": None if self.kind is None else self.kind.value,
            "stage_key": self.stage_key,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "mismatched_engine_version": self.mismatched_engine_version,
            "process_restart_marker": self.process_restart_marker,
            "duplicate_count": self.duplicate_count,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class FaultInjectionController:
    """Applies a profile during Mock Lab reliability tests."""

    profile: MockFaultInjectionProfile = field(default_factory=MockFaultInjectionProfile)
    environment: str = "test"
    stage_completion_counts: dict[tuple[int, str], int] = field(default_factory=dict)
    asset_write_counts: dict[tuple[int, str], int] = field(default_factory=dict)
    task_registry: dict[int, str] = field(default_factory=dict)
    restart_seen: bool = False

    def __post_init__(self) -> None:
        assert_fault_injection_allowed(environment=self.environment)

    def set_profile(self, profile: MockFaultInjectionProfile) -> None:
        assert_fault_injection_allowed(environment=self.environment)
        self.profile = profile

    def should_fail(self, stage_key: str) -> bool:
        return (
            self.profile.enabled
            and self.profile.kind == FaultInjectionKind.FAIL_AT_STAGE
            and self.profile.stage_key == stage_key
        )

    def should_interrupt(self, stage_key: str) -> bool:
        return (
            self.profile.enabled
            and self.profile.kind == FaultInjectionKind.INTERRUPT_AT_STAGE
            and self.profile.stage_key == stage_key
        )

    def should_pause(self, stage_key: str) -> bool:
        return (
            self.profile.enabled
            and self.profile.kind == FaultInjectionKind.PAUSE_AT_STAGE
            and self.profile.stage_key == stage_key
        )

    def should_deny_budget(self, stage_key: str) -> bool:
        return (
            self.profile.enabled
            and self.profile.kind == FaultInjectionKind.BUDGET_DENIED_AT_STAGE
            and self.profile.stage_key == stage_key
        )

    def checkpoint_override(self) -> str | None:
        if (
            self.profile.enabled
            and self.profile.kind == FaultInjectionKind.CORRUPTED_CHECKPOINT
        ):
            return self.profile.corrupt_checkpoint_blob
        return None

    def engine_version_for_recovery(self) -> str:
        if (
            self.profile.enabled
            and self.profile.kind == FaultInjectionKind.ENGINE_VERSION_MISMATCH
        ):
            return self.profile.mismatched_engine_version
        return self.profile.engine_version

    def note_stage_completion(self, run_id: int, stage_key: str) -> int:
        key = (run_id, stage_key)
        self.stage_completion_counts[key] = self.stage_completion_counts.get(key, 0) + 1
        return self.stage_completion_counts[key]

    def note_asset_write(self, run_id: int, asset_key: str) -> int:
        key = (run_id, asset_key)
        self.asset_write_counts[key] = self.asset_write_counts.get(key, 0) + 1
        return self.asset_write_counts[key]

    def simulate_duplicate_stage_completion(self, run_id: int, stage_key: str) -> int:
        if self.profile.kind != FaultInjectionKind.DUPLICATE_STAGE_COMPLETION:
            return self.note_stage_completion(run_id, stage_key)
        count = 0
        for _ in range(self.profile.duplicate_count):
            count = self.note_stage_completion(run_id, stage_key)
        return count

    def simulate_duplicate_asset_write(self, run_id: int, asset_key: str) -> int:
        if self.profile.kind != FaultInjectionKind.DUPLICATE_ASSET_WRITE:
            return self.note_asset_write(run_id, asset_key)
        count = 0
        for _ in range(self.profile.duplicate_count):
            count = self.note_asset_write(run_id, asset_key)
        return count

    def register_task(self, run_id: int, handle: str = "local-task") -> None:
        self.task_registry[run_id] = handle

    def simulate_task_registry_loss(self) -> None:
        if self.profile.kind == FaultInjectionKind.TASK_REGISTRY_LOSS:
            self.task_registry.clear()

    def mark_process_restart(self) -> str:
        marker = self.profile.process_restart_marker or "process_restarted"
        self.restart_seen = True
        return marker

    def apply_stage_outcome(self, stage_key: str) -> str:
        """Return deterministic outcome token for a stage under current profile."""
        if self.should_fail(stage_key):
            return "failed"
        if self.should_interrupt(stage_key):
            return "interrupted"
        if self.should_pause(stage_key):
            return "paused"
        if self.should_deny_budget(stage_key):
            return "budget_denied"
        return "completed"


def default_stage_key() -> str:
    return WholeBookStageKey.RESOLVE_ENTITIES.value


def build_profile(
    kind: FaultInjectionKind,
    *,
    stage_key: str | None = None,
    **kwargs: Any,
) -> MockFaultInjectionProfile:
    return MockFaultInjectionProfile(
        kind=kind,
        stage_key=stage_key or default_stage_key(),
        **kwargs,
    )


__all__ = [
    "FaultInjectionController",
    "FaultInjectionKind",
    "MockFaultInjectionProfile",
    "assert_fault_injection_allowed",
    "build_profile",
    "default_stage_key",
]
