"""Mock Run audit event contract (Phase 2A-P).

May use Run/Stage metadata, structured logs, or test Audit Sink.
No new formal audit DB tables. No novel body / credentials / prompts / evidence full text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MockRunAuditEventType(StrEnum):
    RUN_CREATED = "run_created"
    RUN_STATE_CHANGED = "run_state_changed"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    STAGE_RETRIED = "stage_retried"
    PAUSE_REQUESTED = "pause_requested"
    RESUME_REQUESTED = "resume_requested"
    CANCEL_REQUESTED = "cancel_requested"
    RECOVERY_SCANNED = "recovery_scanned"
    BUDGET_DENIED = "budget_denied"


FORBIDDEN_AUDIT_CONTENT_TOKENS: frozenset[str] = frozenset(
    {
        "full_text",
        "novel_body",
        "api_key",
        "credential",
        "system_prompt",
        "evidence_full_text",
    }
)


@dataclass(frozen=True, slots=True)
class MockRunAuditEvent:
    event_id: str
    run_id: int
    event_type: MockRunAuditEventType
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
    detail_message: str | None = None

    def __post_init__(self) -> None:
        if not self.mock or not self.non_production:
            raise ValueError("audit event must be mock/non_production")
        if not self.event_id.strip():
            raise ValueError("event_id required")
        blob = " ".join(
            filter(
                None,
                [self.detail_code, self.detail_message, self.actor, self.stage_key],
            )
        ).lower()
        if any(token in blob for token in FORBIDDEN_AUDIT_CONTENT_TOKENS):
            raise ValueError("audit must not contain forbidden content tokens")
        if self.detail_message and len(self.detail_message) > 500:
            raise ValueError("audit detail_message too long")


AUDIT_SINK_OPTIONS: tuple[str, ...] = (
    "run_stage_metadata",
    "structured_logs",
    "test_audit_sink",
)

NO_NEW_AUDIT_TABLE = True
