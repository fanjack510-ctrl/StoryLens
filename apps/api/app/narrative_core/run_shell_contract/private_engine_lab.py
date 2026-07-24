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
