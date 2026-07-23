"""InProcessMockRunTaskRegistry contract (Phase 2A-P).

Registry holds in-process handles only. Database remains source of truth.
No task object serialization to DB. Non-production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class MockTaskHandleStatus(StrEnum):
    REGISTERED = "registered"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    CANCEL_REQUESTED = "cancel_requested"
    FINISHED = "finished"


@dataclass(frozen=True, slots=True)
class MockTaskHandle:
    run_id: int
    status: MockTaskHandleStatus
    non_production: bool = True
    process_local: bool = True

    def __post_init__(self) -> None:
        if not self.non_production or not self.process_local:
            raise ValueError("task handle must be process-local and non_production")


@runtime_checkable
class InProcessMockRunTaskRegistry(Protocol):
    def register(self, run_id: int) -> MockTaskHandle: ...

    def get(self, run_id: int) -> MockTaskHandle | None: ...

    def list(self) -> tuple[MockTaskHandle, ...]: ...

    def request_pause(self, run_id: int) -> MockTaskHandle: ...

    def request_cancel(self, run_id: int) -> MockTaskHandle: ...

    def mark_finished(self, run_id: int) -> MockTaskHandle: ...

    def remove_finished(self, run_id: int) -> bool: ...

    def recover_unfinished(self) -> tuple[int, ...]: ...


TASK_REGISTRY_PROTOCOL_METHODS: tuple[str, ...] = (
    "register",
    "get",
    "list",
    "request_pause",
    "request_cancel",
    "mark_finished",
    "remove_finished",
    "recover_unfinished",
)


@dataclass
class InMemoryMockRunTaskRegistryFixture:
    """Contract fixture: one run_id → one handle; register is idempotent."""

    _handles: dict[int, MockTaskHandle] = field(default_factory=dict)
    non_production: bool = True

    def register(self, run_id: int) -> MockTaskHandle:
        existing = self._handles.get(run_id)
        if existing is not None and existing.status != MockTaskHandleStatus.FINISHED:
            return existing
        handle = MockTaskHandle(run_id=run_id, status=MockTaskHandleStatus.REGISTERED)
        self._handles[run_id] = handle
        return handle

    def get(self, run_id: int) -> MockTaskHandle | None:
        return self._handles.get(run_id)

    def list(self) -> tuple[MockTaskHandle, ...]:
        return tuple(self._handles.values())

    def request_pause(self, run_id: int) -> MockTaskHandle:
        return self._set(run_id, MockTaskHandleStatus.PAUSE_REQUESTED)

    def request_cancel(self, run_id: int) -> MockTaskHandle:
        return self._set(run_id, MockTaskHandleStatus.CANCEL_REQUESTED)

    def mark_finished(self, run_id: int) -> MockTaskHandle:
        return self._set(run_id, MockTaskHandleStatus.FINISHED)

    def remove_finished(self, run_id: int) -> bool:
        handle = self._handles.get(run_id)
        if handle is None or handle.status != MockTaskHandleStatus.FINISHED:
            return False
        del self._handles[run_id]
        return True

    def recover_unfinished(self) -> tuple[int, ...]:
        # Registry cannot restore factual state after restart; returns unfinished ids only.
        return tuple(
            h.run_id
            for h in self._handles.values()
            if h.status != MockTaskHandleStatus.FINISHED
        )

    def _set(self, run_id: int, status: MockTaskHandleStatus) -> MockTaskHandle:
        if run_id not in self._handles:
            self.register(run_id)
        handle = MockTaskHandle(run_id=run_id, status=status)
        self._handles[run_id] = handle
        return handle


TASK_REGISTRY_RULES: tuple[str, ...] = (
    "registry_holds_process_handles_only",
    "database_is_source_of_truth",
    "restart_must_not_rely_on_memory_registry_for_facts",
    "unfinished_runs_recover_via_db_and_checkpoint",
    "one_run_id_one_execution_task",
    "register_idempotent",
    "shutdown_marks_running_stage_interrupted",
    "do_not_serialize_task_objects_to_db",
    "no_new_background_service_dependency",
    "non_production",
)
