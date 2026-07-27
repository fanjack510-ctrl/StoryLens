"""Phase 2A-P Mock Run Shell error codes (stable API / Lab contract).

Messages must be user-safe: no full novel body, credentials, prompts, or stacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MockRunErrorCode(StrEnum):
    MOCK_LAB_DISABLED = "MOCK_LAB_DISABLED"
    MOCK_LAB_ENVIRONMENT_NOT_ALLOWED = "MOCK_LAB_ENVIRONMENT_NOT_ALLOWED"
    MOCK_LAB_LOOPBACK_REQUIRED = "MOCK_LAB_LOOPBACK_REQUIRED"
    MOCK_LAB_REQUEST_MARKER_REQUIRED = "MOCK_LAB_REQUEST_MARKER_REQUIRED"
    MOCK_LAB_ENGINE_REQUIRED = "MOCK_LAB_ENGINE_REQUIRED"
    MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE = "MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE"
    MOCK_ENGINE_REQUIRED = "MOCK_ENGINE_REQUIRED"
    MOCK_RUN_NOT_FOUND = "MOCK_RUN_NOT_FOUND"
    MOCK_RUN_ALREADY_ACTIVE = "MOCK_RUN_ALREADY_ACTIVE"
    MOCK_RUN_STATE_CONFLICT = "MOCK_RUN_STATE_CONFLICT"
    MOCK_RUN_OPERATION_NOT_ALLOWED = "MOCK_RUN_OPERATION_NOT_ALLOWED"
    MOCK_RUN_IDEMPOTENCY_CONFLICT = "MOCK_RUN_IDEMPOTENCY_CONFLICT"
    MOCK_RUN_SNAPSHOT_INVALID = "MOCK_RUN_SNAPSHOT_INVALID"
    MOCK_RUN_CHECKPOINT_INVALID = "MOCK_RUN_CHECKPOINT_INVALID"
    MOCK_RUN_ENGINE_VERSION_MISMATCH = "MOCK_RUN_ENGINE_VERSION_MISMATCH"
    MOCK_RUN_BUDGET_EXCEEDED = "MOCK_RUN_BUDGET_EXCEEDED"
    MOCK_RUN_CANCELLED = "MOCK_RUN_CANCELLED"
    MOCK_RUN_NOT_RECOVERABLE = "MOCK_RUN_NOT_RECOVERABLE"
    MOCK_RUN_NON_MOCK_TARGET = "MOCK_RUN_NON_MOCK_TARGET"


MOCK_RUN_ERROR_MESSAGES: dict[MockRunErrorCode, str] = {
    MockRunErrorCode.MOCK_LAB_DISABLED: "Mock Lab is disabled. Set WHOLE_BOOK_MOCK_LAB_ENABLED only in development/test.",
    MockRunErrorCode.MOCK_LAB_ENVIRONMENT_NOT_ALLOWED: "Mock Lab is not allowed in this application environment.",
    MockRunErrorCode.MOCK_LAB_LOOPBACK_REQUIRED: "Mock Lab write requests must originate from loopback.",
    MockRunErrorCode.MOCK_LAB_REQUEST_MARKER_REQUIRED: "Mock Lab request marker is required.",
    MockRunErrorCode.MOCK_LAB_ENGINE_REQUIRED: "Mock Lab requires MockWholeBookAnalysisEngine.",
    MockRunErrorCode.MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE: "Requested engine is not marked non_production.",
    MockRunErrorCode.MOCK_ENGINE_REQUIRED: "A mock whole-book engine is required for this operation.",
    MockRunErrorCode.MOCK_RUN_NOT_FOUND: "Mock run was not found.",
    MockRunErrorCode.MOCK_RUN_ALREADY_ACTIVE: "An active mock run already exists for this book.",
    MockRunErrorCode.MOCK_RUN_STATE_CONFLICT: "Run state conflict; expected_state/version did not match.",
    MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED: "Operation is not allowed for the current run state.",
    MockRunErrorCode.MOCK_RUN_IDEMPOTENCY_CONFLICT: "Idempotency key conflicts with a different request payload.",
    MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID: "Book snapshot is missing, mismatched, or not completed.",
    MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID: "Checkpoint is missing or schema/version incompatible.",
    MockRunErrorCode.MOCK_RUN_ENGINE_VERSION_MISMATCH: "Engine id/version does not match the run record.",
    MockRunErrorCode.MOCK_RUN_BUDGET_EXCEEDED: "Mock synthetic budget exceeded; no assets were written.",
    MockRunErrorCode.MOCK_RUN_CANCELLED: "Mock run was cancelled.",
    MockRunErrorCode.MOCK_RUN_NOT_RECOVERABLE: "Mock run cannot be recovered.",
    MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET: "Target run is not a mock lab run.",
}


@dataclass(frozen=True, slots=True)
class MockRunError:
    code: MockRunErrorCode
    message: str
    detail_code: str | None = None
    run_id: int | None = None
    stage_key: str | None = None

    def __post_init__(self) -> None:
        if len(self.message) > 500:
            raise ValueError("error message must stay short (no novel body)")
        forbidden = ("api_key", "authorization:", "prompt=", "full_text", "novel_body")
        lower = self.message.lower()
        if any(token in lower for token in forbidden):
            raise ValueError("error message must not leak credentials or body")


def mock_run_error(code: MockRunErrorCode, **kwargs: object) -> MockRunError:
    message = MOCK_RUN_ERROR_MESSAGES[code]
    return MockRunError(code=code, message=message, **kwargs)  # type: ignore[arg-type]


def all_mock_run_error_codes() -> tuple[str, ...]:
    return tuple(sorted(code.value for code in MockRunErrorCode))
