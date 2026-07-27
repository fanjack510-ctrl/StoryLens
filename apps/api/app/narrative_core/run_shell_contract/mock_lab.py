"""Mock Lab authorization gate (Phase 2A-P).

Independent of production ship gates. Default closed.
Does not mutate Capability metadata, License, or commercial quota.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from app.narrative_core.run_shell_contract.errors import MockRunErrorCode

# Non-production Lab flag. Default false; release builds must keep closed.
WHOLE_BOOK_MOCK_LAB_ENABLED: bool = False

MOCK_LAB_REQUEST_MARKER_HEADER = "X-StoryLens-Mock-Lab"
MOCK_LAB_REQUEST_MARKER_VALUE = "1"
MOCK_ENGINE_ID = "mock_whole_book_v0"
MOCK_LAB_SOURCE = "mock_lab"

ALLOWED_MOCK_LAB_ENVIRONMENTS: frozenset[str] = frozenset({"development", "test"})


class MockLabDenyReason(StrEnum):
    MOCK_LAB_DISABLED = MockRunErrorCode.MOCK_LAB_DISABLED.value
    MOCK_LAB_ENVIRONMENT_NOT_ALLOWED = MockRunErrorCode.MOCK_LAB_ENVIRONMENT_NOT_ALLOWED.value
    MOCK_LAB_LOOPBACK_REQUIRED = MockRunErrorCode.MOCK_LAB_LOOPBACK_REQUIRED.value
    MOCK_LAB_ENGINE_REQUIRED = MockRunErrorCode.MOCK_LAB_ENGINE_REQUIRED.value
    MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE = (
        MockRunErrorCode.MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE.value
    )
    MOCK_LAB_REQUEST_MARKER_REQUIRED = MockRunErrorCode.MOCK_LAB_REQUEST_MARKER_REQUIRED.value


@dataclass(frozen=True, slots=True)
class MockLabAuthorizationDecision:
    allowed: bool
    reason_code: str | None
    environment: str
    loopback: bool
    lab_enabled: bool
    requested_engine_id: str | None
    engine_is_mock: bool
    non_production: bool
    evaluated_at: str
    request_marker_present: bool = False
    capability_context_is_lab: bool = False

    def __post_init__(self) -> None:
        if self.allowed and self.reason_code is not None:
            raise ValueError("allowed decision must not carry reason_code")
        if not self.allowed and not self.reason_code:
            raise ValueError("denied decision requires reason_code")


@dataclass(frozen=True, slots=True)
class MockLabAuthorizationInput:
    environment: str
    loopback: bool
    lab_enabled: bool
    request_marker_present: bool
    requested_engine_id: str | None
    engine_is_mock: bool
    engine_non_production: bool
    capability_context_is_lab: bool = True
    snapshot_completed: bool = True


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def evaluate_mock_lab_authorization(
    inp: MockLabAuthorizationInput,
    *,
    evaluated_at: str | None = None,
) -> MockLabAuthorizationDecision:
    """Fail-closed Lab gate. Does not change Capability / License / ship flags."""
    at = evaluated_at or _utc_now_iso()
    base = {
        "environment": inp.environment,
        "loopback": inp.loopback,
        "lab_enabled": inp.lab_enabled,
        "requested_engine_id": inp.requested_engine_id,
        "engine_is_mock": inp.engine_is_mock,
        "non_production": inp.engine_non_production,
        "evaluated_at": at,
        "request_marker_present": inp.request_marker_present,
        "capability_context_is_lab": inp.capability_context_is_lab,
    }

    if not inp.lab_enabled:
        return MockLabAuthorizationDecision(
            allowed=False,
            reason_code=MockLabDenyReason.MOCK_LAB_DISABLED.value,
            **base,
        )
    if inp.environment not in ALLOWED_MOCK_LAB_ENVIRONMENTS:
        return MockLabAuthorizationDecision(
            allowed=False,
            reason_code=MockLabDenyReason.MOCK_LAB_ENVIRONMENT_NOT_ALLOWED.value,
            **base,
        )
    if not inp.loopback:
        return MockLabAuthorizationDecision(
            allowed=False,
            reason_code=MockLabDenyReason.MOCK_LAB_LOOPBACK_REQUIRED.value,
            **base,
        )
    if not inp.request_marker_present:
        return MockLabAuthorizationDecision(
            allowed=False,
            reason_code=MockLabDenyReason.MOCK_LAB_REQUEST_MARKER_REQUIRED.value,
            **base,
        )
    if not inp.engine_is_mock or inp.requested_engine_id != MOCK_ENGINE_ID:
        return MockLabAuthorizationDecision(
            allowed=False,
            reason_code=MockLabDenyReason.MOCK_LAB_ENGINE_REQUIRED.value,
            **base,
        )
    if not inp.engine_non_production:
        return MockLabAuthorizationDecision(
            allowed=False,
            reason_code=MockLabDenyReason.MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE.value,
            **base,
        )

    return MockLabAuthorizationDecision(allowed=True, reason_code=None, **base)


# Lab must never flip these production gates (asserted by contract tests).
LAB_MUST_NOT_MUTATE = (
    "PRO_CAPABILITIES_SHIPPED",
    "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED",
    "PRODUCTION_DEFAULT_ENGINE_ID",
    "whole_book_analysis shipped metadata",
    "formal license persistence",
    "commercial usage counters",
)
