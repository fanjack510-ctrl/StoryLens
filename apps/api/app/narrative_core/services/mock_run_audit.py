"""Mock Run audit sink (Phase 2A Agent O).

Uses structured in-memory events + optional structured logging.
No new audit DB table. Never logs novel body / prompts / credentials.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping

from app.narrative_core.run_shell_contract.audit import (
    FORBIDDEN_AUDIT_CONTENT_TOKENS,
    NO_NEW_AUDIT_TABLE,
)

logger = logging.getLogger("storylens.mock_run_audit")


class MockRunAuditEventName(StrEnum):
    """Full Agent O audit catalog (superset of Phase 2A-P enum)."""

    RUN_CREATED = "run_created"
    RUN_STARTED = "run_started"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    RESUMED = "resumed"
    RETRY_REQUESTED = "retry_requested"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    RECOVERY_PLANNED = "recovery_planned"
    RECOVERY_REJECTED = "recovery_rejected"
    RUN_COMPLETED = "run_completed"
    BUDGET_DENIED = "budget_denied"


@dataclass(frozen=True, slots=True)
class MockRunAuditRecord:
    event_id: str
    run_id: int
    event_type: str
    previous_state: str | None
    new_state: str | None
    stage_key: str | None
    attempt: int | None
    actor: str
    mock: bool
    non_production: bool
    idempotency_key: str | None
    occurred_at: str
    detail_code: str | None = None

    def __post_init__(self) -> None:
        if not self.mock or not self.non_production:
            raise ValueError("audit record must be mock/non_production")
        if not self.event_id.strip():
            raise ValueError("event_id required")
        blob = " ".join(
            filter(
                None,
                [self.detail_code, self.actor, self.stage_key, self.event_type],
            )
        ).lower()
        if any(token in blob for token in FORBIDDEN_AUDIT_CONTENT_TOKENS):
            raise ValueError("audit must not contain forbidden content tokens")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _assert_no_sensitive_payload(payload: Mapping[str, Any] | None) -> None:
    if not payload:
        return
    for key in payload:
        lower = str(key).lower()
        if lower in FORBIDDEN_AUDIT_CONTENT_TOKENS:
            raise ValueError(f"audit payload forbids key: {key}")
        if lower in {"prompt", "system_prompt", "full_text", "novel_body", "api_key"}:
            raise ValueError(f"audit payload forbids key: {key}")


class MockRunAuditSink:
    """In-memory + structured-log audit sink for Mock Lab runs."""

    no_new_audit_table = NO_NEW_AUDIT_TABLE

    def __init__(self, *, emit_logs: bool = True) -> None:
        self._lock = threading.RLock()
        self._events: list[MockRunAuditRecord] = []
        self._emit_logs = emit_logs

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def list_events(self, run_id: int | None = None) -> tuple[MockRunAuditRecord, ...]:
        with self._lock:
            if run_id is None:
                return tuple(self._events)
            return tuple(e for e in self._events if e.run_id == run_id)

    def emit(
        self,
        *,
        run_id: int,
        event_type: MockRunAuditEventName | str,
        actor: str,
        previous_state: str | None = None,
        new_state: str | None = None,
        stage_key: str | None = None,
        attempt: int | None = None,
        idempotency_key: str | None = None,
        detail_code: str | None = None,
        occurred_at: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> MockRunAuditRecord:
        _assert_no_sensitive_payload(extra)
        record = MockRunAuditRecord(
            event_id=uuid.uuid4().hex,
            run_id=int(run_id),
            event_type=str(event_type),
            previous_state=previous_state,
            new_state=new_state,
            stage_key=stage_key,
            attempt=attempt,
            actor=actor,
            mock=True,
            non_production=True,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at or _utc_now_iso(),
            detail_code=detail_code,
        )
        with self._lock:
            self._events.append(record)
        if self._emit_logs:
            safe = asdict(record)
            if extra:
                safe["extra_keys"] = sorted(str(k) for k in extra.keys())
            logger.info("mock_run_audit %s", safe)
        return record

    # Convenience wrappers -------------------------------------------------

    def run_created(self, run_id: int, *, actor: str, idempotency_key: str | None = None) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.RUN_CREATED,
            actor=actor,
            new_state="pending",
            idempotency_key=idempotency_key,
        )

    def run_started(self, run_id: int, *, actor: str, previous_state: str = "pending") -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.RUN_STARTED,
            actor=actor,
            previous_state=previous_state,
            new_state="running",
        )

    def stage_started(
        self, run_id: int, *, stage_key: str, attempt: int, actor: str = "executor"
    ) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.STAGE_STARTED,
            actor=actor,
            stage_key=stage_key,
            attempt=attempt,
            new_state="running",
        )

    def stage_completed(
        self, run_id: int, *, stage_key: str, attempt: int, actor: str = "executor"
    ) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.STAGE_COMPLETED,
            actor=actor,
            stage_key=stage_key,
            attempt=attempt,
            new_state="completed",
        )

    def stage_failed(
        self,
        run_id: int,
        *,
        stage_key: str,
        attempt: int,
        detail_code: str | None = None,
        actor: str = "executor",
    ) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.STAGE_FAILED,
            actor=actor,
            stage_key=stage_key,
            attempt=attempt,
            new_state="failed",
            detail_code=detail_code,
        )

    def pause_requested(self, run_id: int, *, actor: str, idempotency_key: str | None = None) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.PAUSE_REQUESTED,
            actor=actor,
            idempotency_key=idempotency_key,
        )

    def paused(self, run_id: int, *, actor: str, previous_state: str = "running") -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.PAUSED,
            actor=actor,
            previous_state=previous_state,
            new_state="paused",
        )

    def resumed(self, run_id: int, *, actor: str, previous_state: str) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.RESUMED,
            actor=actor,
            previous_state=previous_state,
            new_state="running",
        )

    def retry_requested(
        self, run_id: int, *, stage_key: str, actor: str, idempotency_key: str | None = None
    ) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.RETRY_REQUESTED,
            actor=actor,
            stage_key=stage_key,
            idempotency_key=idempotency_key,
        )

    def cancel_requested(self, run_id: int, *, actor: str, idempotency_key: str | None = None) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.CANCEL_REQUESTED,
            actor=actor,
            idempotency_key=idempotency_key,
        )

    def cancelled(self, run_id: int, *, actor: str, previous_state: str) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.CANCELLED,
            actor=actor,
            previous_state=previous_state,
            new_state="cancelled",
        )

    def interrupted(self, run_id: int, *, actor: str = "startup", previous_state: str = "running") -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.INTERRUPTED,
            actor=actor,
            previous_state=previous_state,
            new_state="interrupted",
            detail_code="PROCESS_INTERRUPTED",
        )

    def recovery_planned(self, run_id: int, *, actor: str, detail_code: str | None = None) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.RECOVERY_PLANNED,
            actor=actor,
            detail_code=detail_code,
        )

    def recovery_rejected(
        self, run_id: int, *, actor: str, detail_code: str | None = None
    ) -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.RECOVERY_REJECTED,
            actor=actor,
            detail_code=detail_code,
        )

    def run_completed(self, run_id: int, *, actor: str = "executor") -> MockRunAuditRecord:
        return self.emit(
            run_id=run_id,
            event_type=MockRunAuditEventName.RUN_COMPLETED,
            actor=actor,
            previous_state="running",
            new_state="completed",
        )


__all__ = [
    "MockRunAuditEventName",
    "MockRunAuditRecord",
    "MockRunAuditSink",
]
