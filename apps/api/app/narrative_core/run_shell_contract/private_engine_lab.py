"""Private Engine Lab authorization gate (Phase 2B-R Agent S).

Distinct from Mock Lab. Default closed. Does not flip production ship gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

# Non-production Private Engine Lab flag. Default false; release builds must keep closed.
WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED: bool = False

PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER = "X-StoryLens-Private-Engine-Lab"
PRIVATE_ENGINE_LAB_REQUEST_MARKER_VALUE = "1"
PRIVATE_ENGINE_LAB_SOURCE = "private_engine_lab"
PRIVATE_ENGINE_LAB_API_PREFIX = "/api/v1/labs/private-whole-book-runs"

# First Provider route (public-side constants; routing tables live in private package).
PRIVATE_LAB_FIRST_PROVIDER_KEY = "aliyun_qwen_plus"
PRIVATE_LAB_FIRST_MODEL_ID = "qwen3.7-plus"
PRIVATE_LAB_FIRST_QUALITY_PROFILE = "balanced"

ALLOWED_PRIVATE_ENGINE_LAB_ENVIRONMENTS: frozenset[str] = frozenset({"development", "test"})

# Opt-in live Provider probe — default off; CI must never require this.
PRIVATE_PROVIDER_LIVE_PROBE_ENV = "WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE"


class PrivateEngineLabDenyReason(StrEnum):
    PRIVATE_ENGINE_LAB_DISABLED = "PRIVATE_ENGINE_LAB_DISABLED"
    PRIVATE_ENGINE_LAB_ENVIRONMENT_NOT_ALLOWED = "PRIVATE_ENGINE_LAB_ENVIRONMENT_NOT_ALLOWED"
    PRIVATE_ENGINE_LAB_LOOPBACK_REQUIRED = "PRIVATE_ENGINE_LAB_LOOPBACK_REQUIRED"
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_REQUIRED = "PRIVATE_ENGINE_LAB_REQUEST_MARKER_REQUIRED"
    PRIVATE_ENGINE_LAB_CREDENTIAL_REQUIRED = "PRIVATE_ENGINE_LAB_CREDENTIAL_REQUIRED"
    PRIVATE_ENGINE_LAB_DATA_TRANSFER_CONSENT_REQUIRED = (
        "PRIVATE_ENGINE_LAB_DATA_TRANSFER_CONSENT_REQUIRED"
    )
    PRIVATE_ENGINE_LAB_BUDGET_DENIED = "PRIVATE_ENGINE_LAB_BUDGET_DENIED"
    PRIVATE_ENGINE_LAB_CAPABILITY_DENIED = "PRIVATE_ENGINE_LAB_CAPABILITY_DENIED"
    PRIVATE_ENGINE_LAB_CONCURRENCY_LIMIT = "PRIVATE_ENGINE_LAB_CONCURRENCY_LIMIT"
    PRIVATE_ENGINE_LAB_CONFIRM_REQUIRED = "PRIVATE_ENGINE_LAB_CONFIRM_REQUIRED"
    PRIVATE_ENGINE_LAB_PREFLIGHT_REJECTED = "PRIVATE_ENGINE_LAB_PREFLIGHT_REJECTED"
    PRIVATE_ENGINE_LAB_ESTIMATE_FINGERPRINT_MISMATCH = (
        "PRIVATE_ENGINE_LAB_ESTIMATE_FINGERPRINT_MISMATCH"
    )
    PRIVATE_ENGINE_LAB_CONSENT_FINGERPRINT_MISMATCH = (
        "PRIVATE_ENGINE_LAB_CONSENT_FINGERPRINT_MISMATCH"
    )
    PRIVATE_ENGINE_LAB_SNAPSHOT_INVALID = "PRIVATE_ENGINE_LAB_SNAPSHOT_INVALID"
    PRIVATE_ENGINE_LAB_NOT_PRIVATE_RUN = "PRIVATE_ENGINE_LAB_NOT_PRIVATE_RUN"
    PRIVATE_ENGINE_LAB_IDEMPOTENCY_CONFLICT = "PRIVATE_ENGINE_LAB_IDEMPOTENCY_CONFLICT"
    PRIVATE_ENGINE_LAB_STATE_CONFLICT = "PRIVATE_ENGINE_LAB_STATE_CONFLICT"
    PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED = "PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED"
    PRIVATE_ENGINE_LAB_CHECKPOINT_INVALID = "PRIVATE_ENGINE_LAB_CHECKPOINT_INVALID"
    PRIVATE_ENGINE_LAB_RUN_NOT_FOUND = "PRIVATE_ENGINE_LAB_RUN_NOT_FOUND"


PRIVATE_ENGINE_LAB_DENY_MESSAGES: dict[PrivateEngineLabDenyReason, str] = {
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_DISABLED: (
        "Private Engine Lab is disabled. Set WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED "
        "only in development/test."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_ENVIRONMENT_NOT_ALLOWED: (
        "Private Engine Lab is not allowed in this application environment."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_LOOPBACK_REQUIRED: (
        "Private Engine Lab write requests must originate from loopback."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_REQUEST_MARKER_REQUIRED: (
        "Private Engine Lab request marker is required."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CREDENTIAL_REQUIRED: (
        "Usable provider credential is required for Private Engine Lab."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_DATA_TRANSFER_CONSENT_REQUIRED: (
        "Data-transfer consent is required before cloud Provider calls."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_BUDGET_DENIED: (
        "Cloud budget denied this Private Engine Lab request."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CAPABILITY_DENIED: (
        "Capability service denied whole-book Private Engine Lab access."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONCURRENCY_LIMIT: (
        "An active Private Engine Lab run already exists for this book."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONFIRM_REQUIRED: (
        "Explicit user confirm is required before starting Private Engine Lab."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_PREFLIGHT_REJECTED: (
        "Private Engine Lab preflight was rejected."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_ESTIMATE_FINGERPRINT_MISMATCH: (
        "Estimate fingerprint does not match the Lab create request."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONSENT_FINGERPRINT_MISMATCH: (
        "Consent fingerprint does not match the data-transfer manifest."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_SNAPSHOT_INVALID: (
        "Book snapshot is missing, incomplete, or not bound to the book."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_NOT_PRIVATE_RUN: (
        "Target AnalysisRun is not a Private Engine Lab run."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_IDEMPOTENCY_CONFLICT: (
        "Idempotency key conflict for Private Engine Lab create."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_STATE_CONFLICT: (
        "Private Engine Lab run state/version conflict."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED: (
        "Operation is not allowed for the current Private Engine Lab run state."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CHECKPOINT_INVALID: (
        "Private Engine Lab checkpoint is invalid or incompatible."
    ),
    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_RUN_NOT_FOUND: (
        "Private Engine Lab run was not found."
    ),
}


@dataclass(frozen=True, slots=True)
class PrivateEngineLabAuthorizationDecision:
    allowed: bool
    reason_code: str | None
    environment: str
    loopback: bool
    lab_enabled: bool
    request_marker_present: bool
    credential_present: bool
    data_transfer_consented: bool
    budget_ok: bool
    capability_ok: bool
    user_confirmed: bool
    non_production: bool
    evaluated_at: str
    provider_key: str = PRIVATE_LAB_FIRST_PROVIDER_KEY
    model_id: str = PRIVATE_LAB_FIRST_MODEL_ID
    quality_profile: str = PRIVATE_LAB_FIRST_QUALITY_PROFILE

    def __post_init__(self) -> None:
        if self.allowed and self.reason_code is not None:
            raise ValueError("allowed decision must not carry reason_code")
        if not self.allowed and not self.reason_code:
            raise ValueError("denied decision requires reason_code")


@dataclass(frozen=True, slots=True)
class PrivateEngineLabAuthorizationInput:
    environment: str
    loopback: bool
    lab_enabled: bool
    request_marker_present: bool
    credential_present: bool
    data_transfer_consented: bool
    budget_ok: bool
    capability_ok: bool
    user_confirmed: bool
    non_production: bool = True
    # Dry Lab probes may skip credential/consent when dry_run=True.
    dry_run: bool = True


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def evaluate_private_engine_lab_authorization(
    inp: PrivateEngineLabAuthorizationInput,
    *,
    evaluated_at: str | None = None,
) -> PrivateEngineLabAuthorizationDecision:
    """Fail-closed Private Engine Lab gate. Does not mutate production ship flags."""
    at = evaluated_at or _utc_now_iso()
    base = {
        "environment": inp.environment,
        "loopback": inp.loopback,
        "lab_enabled": inp.lab_enabled,
        "request_marker_present": inp.request_marker_present,
        "credential_present": inp.credential_present,
        "data_transfer_consented": inp.data_transfer_consented,
        "budget_ok": inp.budget_ok,
        "capability_ok": inp.capability_ok,
        "user_confirmed": inp.user_confirmed,
        "non_production": inp.non_production,
        "evaluated_at": at,
    }

    if not inp.lab_enabled:
        return PrivateEngineLabAuthorizationDecision(
            allowed=False,
            reason_code=PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_DISABLED.value,
            **base,
        )
    if inp.environment not in ALLOWED_PRIVATE_ENGINE_LAB_ENVIRONMENTS:
        return PrivateEngineLabAuthorizationDecision(
            allowed=False,
            reason_code=PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_ENVIRONMENT_NOT_ALLOWED.value,
            **base,
        )
    if not inp.loopback:
        return PrivateEngineLabAuthorizationDecision(
            allowed=False,
            reason_code=PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_LOOPBACK_REQUIRED.value,
            **base,
        )
    if not inp.request_marker_present:
        return PrivateEngineLabAuthorizationDecision(
            allowed=False,
            reason_code=PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_REQUEST_MARKER_REQUIRED.value,
            **base,
        )
    if not inp.non_production:
        return PrivateEngineLabAuthorizationDecision(
            allowed=False,
            reason_code=PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_ENVIRONMENT_NOT_ALLOWED.value,
            **base,
        )
    if not inp.capability_ok:
        return PrivateEngineLabAuthorizationDecision(
            allowed=False,
            reason_code=PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CAPABILITY_DENIED.value,
            **base,
        )
    if not inp.dry_run:
        if not inp.credential_present:
            return PrivateEngineLabAuthorizationDecision(
                allowed=False,
                reason_code=PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CREDENTIAL_REQUIRED.value,
                **base,
            )
        if not inp.data_transfer_consented:
            return PrivateEngineLabAuthorizationDecision(
                allowed=False,
                reason_code=PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_DATA_TRANSFER_CONSENT_REQUIRED.value,
                **base,
            )
        if not inp.user_confirmed:
            return PrivateEngineLabAuthorizationDecision(
                allowed=False,
                reason_code=PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONFIRM_REQUIRED.value,
                **base,
            )
        if not inp.budget_ok:
            return PrivateEngineLabAuthorizationDecision(
                allowed=False,
                reason_code=PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_BUDGET_DENIED.value,
                **base,
            )

    return PrivateEngineLabAuthorizationDecision(allowed=True, reason_code=None, **base)


# Lab must never flip these production gates (asserted by contract tests).
PRIVATE_ENGINE_LAB_MUST_NOT_MUTATE = (
    "PRO_CAPABILITIES_SHIPPED",
    "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED",
    "PRODUCTION_DEFAULT_ENGINE_ID",
    "WHOLE_BOOK_MOCK_LAB_ENABLED",
    "whole_book_analysis shipped metadata",
    "formal license persistence",
    "commercial usage counters",
)

OPENAPI_PRIVATE_ENGINE_LAB_TAGS: tuple[str, ...] = (
    "labs",
    "non-production",
    "private-engine-lab",
)


# --- Phase 2B-R1 Agent V: Lab run create / metadata (no U estimate logic) ---

PRIVATE_LAB_ENGINE_ID = "storylens.private.whole_book.dev"
PRIVATE_LAB_ENGINE_VERSION = "0.1.0-dev"
PRIVATE_LAB_RUN_METADATA_SCHEMA = "private_whole_book_lab_run_metadata"
PRIVATE_LAB_RUN_METADATA_VERSION = "1.0.0"
PRIVATE_LAB_RUN_METADATA_ENVELOPE_KEY = "private_whole_book_lab_run_metadata"
PRIVATE_LAB_TASK_TYPE = "whole_book_private_lab"

CREATE_PRIVATE_LAB_RUN_SEQUENCE: tuple[str, ...] = (
    "authorize",
    "validate_preflight_result",
    "validate_estimate_fingerprint",
    "validate_consent_fingerprint",
    "validate_credential_status",
    "validate_budget_status",
    "validate_snapshot_completed",
    "bind_snapshot_book",
    "reserve_concurrency",
    "create_analysis_run",
    "create_analysis_run_stages",
    "register_execution_task",
    "start_executor",
)

PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER: tuple[str, ...] = (
    "book_overview",
    "structure_stages",
    "chapter_functions",
    "storylines",
)
