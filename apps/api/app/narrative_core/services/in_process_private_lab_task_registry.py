"""In-process Private Lab Task Registry (Phase 2B-R1 Agent V).

Process-local handles only. DB remains factual source of truth.
Distinct from Mock Lab registry. Non-production.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable


class PrivateLabTaskHandleStatus(StrEnum):
    REGISTERED = "registered"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    CANCEL_REQUESTED = "cancel_requested"
    FINISHED = "finished"


@dataclass
class PrivateLabTaskHandle:
    run_id: int
    status: PrivateLabTaskHandleStatus
    registered_at: str
    updated_at: str
    cancellation_ref: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class InProcessPrivateLabTaskRegistry:
    """One run_id → one unfinished task handle; register is idempotent."""

    def __init__(self, *, non_production: bool = True) -> None:
        if not non_production:
            raise ValueError("InProcessPrivateLabTaskRegistry must be non_production")
        self.non_production = True
        self._lock = threading.RLock()
        self._handles: dict[int, PrivateLabTaskHandle] = {}
        self._pause_flags: dict[int, bool] = {}
        self._cancel_flags: dict[int, bool] = {}
        self._on_shutdown: Callable[[], None] | None = None

    def register(self, run_id: int, *, cancellation_ref: str | None = None) -> PrivateLabTaskHandle:
        rid = int(run_id)
        now = _utc_now_iso()
        with self._lock:
            existing = self._handles.get(rid)
            if existing is not None and existing.status != PrivateLabTaskHandleStatus.FINISHED:
                return existing
            handle = PrivateLabTaskHandle(
                run_id=rid,
                status=PrivateLabTaskHandleStatus.REGISTERED,
                registered_at=now,
                updated_at=now,
                cancellation_ref=cancellation_ref or f"private-lab-cancel:{rid}",
            )
            self._handles[rid] = handle
            self._pause_flags.setdefault(rid, False)
            self._cancel_flags.setdefault(rid, False)
            return handle

    def get(self, run_id: int) -> PrivateLabTaskHandle | None:
        with self._lock:
            return self._handles.get(int(run_id))

    def list(self) -> tuple[PrivateLabTaskHandle, ...]:
        with self._lock:
            return tuple(self._handles.values())

    def mark_running(self, run_id: int) -> PrivateLabTaskHandle:
        return self._set(int(run_id), PrivateLabTaskHandleStatus.RUNNING)

    def request_pause(self, run_id: int) -> PrivateLabTaskHandle:
        rid = int(run_id)
        with self._lock:
            self._pause_flags[rid] = True
            return self._set_unlocked(rid, PrivateLabTaskHandleStatus.PAUSE_REQUESTED)

    def request_cancel(self, run_id: int) -> PrivateLabTaskHandle:
        rid = int(run_id)
        with self._lock:
            self._cancel_flags[rid] = True
            return self._set_unlocked(rid, PrivateLabTaskHandleStatus.CANCEL_REQUESTED)

    def clear_pause_request(self, run_id: int) -> None:
        with self._lock:
            self._pause_flags[int(run_id)] = False

    def is_pause_requested(self, run_id: int) -> bool:
        with self._lock:
            return bool(self._pause_flags.get(int(run_id), False))

    def is_cancel_requested(self, run_id: int) -> bool:
        with self._lock:
            return bool(self._cancel_flags.get(int(run_id), False))

    def mark_finished(self, run_id: int) -> PrivateLabTaskHandle:
        rid = int(run_id)
        with self._lock:
            self._pause_flags[rid] = False
            self._cancel_flags[rid] = False
            return self._set_unlocked(rid, PrivateLabTaskHandleStatus.FINISHED)

    def remove_finished(self, run_id: int) -> bool:
        rid = int(run_id)
        with self._lock:
            handle = self._handles.get(rid)
            if handle is None or handle.status != PrivateLabTaskHandleStatus.FINISHED:
                return False
            del self._handles[rid]
            self._pause_flags.pop(rid, None)
            self._cancel_flags.pop(rid, None)
            return True

    def recover_unfinished(self) -> tuple[int, ...]:
        with self._lock:
            return tuple(
                h.run_id
                for h in self._handles.values()
                if h.status != PrivateLabTaskHandleStatus.FINISHED
            )

    def request_cooperative_interrupt_all(self) -> tuple[int, ...]:
        unfinished = self.recover_unfinished()
        for run_id in unfinished:
            self.request_cancel(run_id)
        return unfinished

    def _set(self, run_id: int, status: PrivateLabTaskHandleStatus) -> PrivateLabTaskHandle:
        with self._lock:
            return self._set_unlocked(run_id, status)

    def _set_unlocked(self, run_id: int, status: PrivateLabTaskHandleStatus) -> PrivateLabTaskHandle:
        now = _utc_now_iso()
        handle = self._handles.get(run_id)
        if handle is None:
            handle = PrivateLabTaskHandle(
                run_id=run_id,
                status=status,
                registered_at=now,
                updated_at=now,
                cancellation_ref=f"private-lab-cancel:{run_id}",
            )
        else:
            handle.status = status
            handle.updated_at = now
        self._handles[run_id] = handle
        return handle


_default_registry: InProcessPrivateLabTaskRegistry | None = None
_default_lock = threading.Lock()


def get_default_private_lab_task_registry() -> InProcessPrivateLabTaskRegistry:
    global _default_registry
    with _default_lock:
        if _default_registry is None:
            _default_registry = InProcessPrivateLabTaskRegistry()
        return _default_registry


def reset_default_private_lab_task_registry() -> None:
    global _default_registry
    with _default_lock:
        _default_registry = InProcessPrivateLabTaskRegistry()


__all__ = [
    "InProcessPrivateLabTaskRegistry",
    "PrivateLabTaskHandle",
    "PrivateLabTaskHandleStatus",
    "get_default_private_lab_task_registry",
    "reset_default_private_lab_task_registry",
]
