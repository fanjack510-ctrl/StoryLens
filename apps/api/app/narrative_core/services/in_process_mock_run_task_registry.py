"""In-process Mock Run Task Registry (Phase 2A Agent M).

Holds process-local handles only. Database remains factual source of truth.
No Celery/Redis/queue. Non-production. Does not serialize Task objects to DB.
"""

from __future__ import annotations

import threading
from typing import Callable

from app.narrative_core.run_shell_contract.task_registry import (
    MockTaskHandle,
    MockTaskHandleStatus,
)


class InProcessMockRunTaskRegistry:
    """One run_id → one unfinished task handle; register is idempotent."""

    def __init__(self, *, non_production: bool = True) -> None:
        if not non_production:
            raise ValueError("InProcessMockRunTaskRegistry must be non_production")
        self.non_production = True
        self._lock = threading.RLock()
        self._handles: dict[int, MockTaskHandle] = {}
        self._pause_flags: dict[int, bool] = {}
        self._cancel_flags: dict[int, bool] = {}
        self._on_shutdown: Callable[[], None] | None = None

    def register(self, run_id: int) -> MockTaskHandle:
        rid = int(run_id)
        with self._lock:
            existing = self._handles.get(rid)
            if existing is not None and existing.status != MockTaskHandleStatus.FINISHED:
                return existing
            handle = MockTaskHandle(run_id=rid, status=MockTaskHandleStatus.REGISTERED)
            self._handles[rid] = handle
            self._pause_flags.setdefault(rid, False)
            self._cancel_flags.setdefault(rid, False)
            return handle

    def get(self, run_id: int) -> MockTaskHandle | None:
        with self._lock:
            return self._handles.get(int(run_id))

    def list(self) -> tuple[MockTaskHandle, ...]:
        with self._lock:
            return tuple(self._handles.values())

    def mark_running(self, run_id: int) -> MockTaskHandle:
        return self._set(int(run_id), MockTaskHandleStatus.RUNNING)

    def request_pause(self, run_id: int) -> MockTaskHandle:
        rid = int(run_id)
        with self._lock:
            self._pause_flags[rid] = True
            return self._set_unlocked(rid, MockTaskHandleStatus.PAUSE_REQUESTED)

    def request_cancel(self, run_id: int) -> MockTaskHandle:
        rid = int(run_id)
        with self._lock:
            self._cancel_flags[rid] = True
            return self._set_unlocked(rid, MockTaskHandleStatus.CANCEL_REQUESTED)

    def clear_pause_request(self, run_id: int) -> None:
        with self._lock:
            self._pause_flags[int(run_id)] = False

    def is_pause_requested(self, run_id: int) -> bool:
        with self._lock:
            return bool(self._pause_flags.get(int(run_id), False))

    def is_cancel_requested(self, run_id: int) -> bool:
        with self._lock:
            return bool(self._cancel_flags.get(int(run_id), False))

    def mark_finished(self, run_id: int) -> MockTaskHandle:
        rid = int(run_id)
        with self._lock:
            self._pause_flags[rid] = False
            self._cancel_flags[rid] = False
            return self._set_unlocked(rid, MockTaskHandleStatus.FINISHED)

    def remove_finished(self, run_id: int) -> bool:
        rid = int(run_id)
        with self._lock:
            handle = self._handles.get(rid)
            if handle is None or handle.status != MockTaskHandleStatus.FINISHED:
                return False
            del self._handles[rid]
            self._pause_flags.pop(rid, None)
            self._cancel_flags.pop(rid, None)
            return True

    def recover_unfinished(self) -> tuple[int, ...]:
        """Return unfinished handle ids only — does not restore DB facts from memory."""
        with self._lock:
            return tuple(
                h.run_id
                for h in self._handles.values()
                if h.status != MockTaskHandleStatus.FINISHED
            )

    def request_cooperative_interrupt_all(self) -> tuple[int, ...]:
        """Shutdown hook: request cancel/interrupt for all unfinished tasks."""
        unfinished = self.recover_unfinished()
        for run_id in unfinished:
            self.request_cancel(run_id)
        return unfinished

    def _set(self, run_id: int, status: MockTaskHandleStatus) -> MockTaskHandle:
        with self._lock:
            return self._set_unlocked(run_id, status)

    def _set_unlocked(self, run_id: int, status: MockTaskHandleStatus) -> MockTaskHandle:
        if run_id not in self._handles:
            self._handles[run_id] = MockTaskHandle(
                run_id=run_id, status=MockTaskHandleStatus.REGISTERED
            )
        handle = MockTaskHandle(run_id=run_id, status=status)
        self._handles[run_id] = handle
        return handle


# Process-wide default for Lab wiring (tests may construct their own).
_DEFAULT_REGISTRY: InProcessMockRunTaskRegistry | None = None
_DEFAULT_LOCK = threading.Lock()


def get_default_mock_run_task_registry() -> InProcessMockRunTaskRegistry:
    global _DEFAULT_REGISTRY
    with _DEFAULT_LOCK:
        if _DEFAULT_REGISTRY is None:
            _DEFAULT_REGISTRY = InProcessMockRunTaskRegistry()
        return _DEFAULT_REGISTRY


def reset_default_mock_run_task_registry() -> None:
    global _DEFAULT_REGISTRY
    with _DEFAULT_LOCK:
        _DEFAULT_REGISTRY = InProcessMockRunTaskRegistry()


__all__ = [
    "InProcessMockRunTaskRegistry",
    "get_default_mock_run_task_registry",
    "reset_default_mock_run_task_registry",
]
