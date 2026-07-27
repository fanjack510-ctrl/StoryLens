"""MockWholeBookRunExecutor protocol + Lab-only test hooks (Phase 2A-P).

No Celery/Redis/distributed queue. Single-process, local, deterministic, non-production.
Test hooks must never appear on production Engine interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.narrative_core.enums import WholeBookStageKey
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus


@dataclass(frozen=True, slots=True)
class MockExecutorTestHooks:
    """Lab-only fault/delay hooks. Forbidden on formal Engine Protocol."""

    stage_delay_ms: int = 0
    fail_at_stage: WholeBookStageKey | None = None
    interrupt_at_stage: WholeBookStageKey | None = None
    pause_at_stage: WholeBookStageKey | None = None
    budget_denied_at_stage: WholeBookStageKey | None = None
    synthetic_output_profile: str = "deterministic_minimal"

    def __post_init__(self) -> None:
        if self.stage_delay_ms < 0:
            raise ValueError("stage_delay_ms must be >= 0")
        if self.stage_delay_ms > 60_000:
            raise ValueError("stage_delay_ms cap 60000 for Lab safety")


@dataclass(frozen=True, slots=True)
class MockExecutionState:
    run_id: int
    status: WholeBookRunViewStatus
    current_stage_key: str | None
    checkpoint_schema: str | None
    checkpoint_version: str | None
    mock: bool = True
    non_production: bool = True
    single_executor: bool = True
    task_registered: bool = False

    def __post_init__(self) -> None:
        if not self.mock or not self.non_production:
            raise ValueError("execution state must be mock/non_production")


@dataclass(frozen=True, slots=True)
class MockExecutorActionResult:
    run_id: int
    accepted: bool
    requested: bool
    current_state: WholeBookRunViewStatus
    detail_code: str | None = None
    stage_key: str | None = None


@runtime_checkable
class MockWholeBookRunExecutor(Protocol):
    def start(self, run_id: int) -> MockExecutorActionResult: ...

    def execute_next_stage(self, run_id: int) -> MockExecutorActionResult: ...

    def execute_until_blocked(self, run_id: int) -> MockExecutorActionResult: ...

    def pause(self, run_id: int) -> MockExecutorActionResult: ...

    def resume(self, run_id: int) -> MockExecutorActionResult: ...

    def retry_stage(self, run_id: int, stage_key: str) -> MockExecutorActionResult: ...

    def cancel(self, run_id: int) -> MockExecutorActionResult: ...

    def recover(self, run_id: int) -> MockExecutorActionResult: ...

    def get_execution_state(self, run_id: int) -> MockExecutionState: ...


EXECUTOR_PROTOCOL_METHODS: tuple[str, ...] = (
    "start",
    "execute_next_stage",
    "execute_until_blocked",
    "pause",
    "resume",
    "retry_stage",
    "cancel",
    "recover",
    "get_execution_state",
)

# Formal Engine Protocol must not include Lab hooks.
FORMAL_ENGINE_FORBIDDEN_HOOK_ATTRS: frozenset[str] = frozenset(
    {
        "stage_delay",
        "stage_delay_ms",
        "fail_at_stage",
        "interrupt_at_stage",
        "pause_at_stage",
        "budget_denied_at_stage",
        "synthetic_output_profile",
        "test_hooks",
    }
)


@dataclass(frozen=True, slots=True)
class MockExecutorConstraints:
    single_process: bool = True
    local_only: bool = True
    deterministic: bool = True
    non_production: bool = True
    testable: bool = True
    recoverable: bool = True
    celery_forbidden: bool = True
    redis_forbidden: bool = True
    distributed_queue_forbidden: bool = True
    cloud_queue_forbidden: bool = True
    multi_machine_forbidden: bool = True


DEFAULT_MOCK_EXECUTOR_CONSTRAINTS = MockExecutorConstraints()


@dataclass
class ProtocolShapeFixture:
    """Minimal structural fixture proving Protocol method names (not a real executor)."""

    hooks: MockExecutorTestHooks = field(default_factory=MockExecutorTestHooks)
    _states: dict[int, MockExecutionState] = field(default_factory=dict)

    def start(self, run_id: int) -> MockExecutorActionResult:
        self._states[run_id] = MockExecutionState(
            run_id=run_id,
            status=WholeBookRunViewStatus.RUNNING,
            current_stage_key=None,
            checkpoint_schema=None,
            checkpoint_version=None,
            task_registered=True,
        )
        return MockExecutorActionResult(
            run_id=run_id,
            accepted=True,
            requested=True,
            current_state=WholeBookRunViewStatus.RUNNING,
        )

    def execute_next_stage(self, run_id: int) -> MockExecutorActionResult:
        return self._action(run_id)

    def execute_until_blocked(self, run_id: int) -> MockExecutorActionResult:
        return self._action(run_id)

    def pause(self, run_id: int) -> MockExecutorActionResult:
        return self._action(run_id, WholeBookRunViewStatus.PAUSED)

    def resume(self, run_id: int) -> MockExecutorActionResult:
        return self._action(run_id, WholeBookRunViewStatus.RUNNING)

    def retry_stage(self, run_id: int, stage_key: str) -> MockExecutorActionResult:
        return self._action(run_id, stage_key=stage_key)

    def cancel(self, run_id: int) -> MockExecutorActionResult:
        return self._action(run_id, WholeBookRunViewStatus.CANCELLED)

    def recover(self, run_id: int) -> MockExecutorActionResult:
        return self._action(run_id)

    def get_execution_state(self, run_id: int) -> MockExecutionState:
        return self._states.get(
            run_id,
            MockExecutionState(
                run_id=run_id,
                status=WholeBookRunViewStatus.PENDING,
                current_stage_key=None,
                checkpoint_schema=None,
                checkpoint_version=None,
            ),
        )

    def _action(
        self,
        run_id: int,
        status: WholeBookRunViewStatus | None = None,
        stage_key: str | None = None,
    ) -> MockExecutorActionResult:
        current = self.get_execution_state(run_id)
        new_status = status or current.status
        self._states[run_id] = MockExecutionState(
            run_id=run_id,
            status=new_status,
            current_stage_key=stage_key or current.current_stage_key,
            checkpoint_schema=current.checkpoint_schema,
            checkpoint_version=current.checkpoint_version,
            task_registered=True,
        )
        return MockExecutorActionResult(
            run_id=run_id,
            accepted=True,
            requested=True,
            current_state=new_status,
            stage_key=stage_key,
        )
