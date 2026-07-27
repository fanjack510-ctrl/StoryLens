"""Provider execution authorization (Phase 2B-R1 CHG-050).

Immutable safety status shared by Lab Adapter / Gateway / Bailian.
Contains no Credential, body, or Prompt.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ProviderExecutionAuthorization:
    """Single source of truth for dry vs live provider execution."""

    environment: str
    private_lab_enabled: bool
    live_probe_enabled: bool
    allow_network: bool
    requested_dry_run: bool
    effective_dry_run: bool
    consent_valid: bool
    estimate_valid: bool
    budget_valid: bool
    credential_valid: bool
    cancellation_requested: bool
    provider_route_valid: bool
    provider_health_allowed: bool
    deny_reason: str | None
    authorization_fingerprint: str

    def safe_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_authorization_fingerprint(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def compute_provider_execution_authorization(
    *,
    environment: str,
    private_lab_enabled: bool,
    live_probe_enabled: bool,
    allow_network: bool,
    requested_dry_run: bool,
    consent_valid: bool = True,
    estimate_valid: bool = True,
    budget_valid: bool = True,
    credential_valid: bool = True,
    cancellation_requested: bool = False,
    provider_route_valid: bool = True,
    provider_health_allowed: bool = True,
) -> ProviderExecutionAuthorization:
    """Derive effective_dry_run from server-side gates only (never client booleans alone)."""

    env = str(environment or "").strip().lower()
    env_ok = env in {"development", "test", "dev"}
    deny: str | None = None

    if cancellation_requested:
        deny = "cancellation_requested"
    elif not env_ok or env == "production":
        deny = "environment_forbidden"
    elif not private_lab_enabled:
        deny = "private_lab_disabled"
    elif not live_probe_enabled:
        deny = "live_probe_disabled"
    elif not allow_network:
        deny = "allow_network_false"
    elif not consent_valid:
        deny = "consent_invalid"
    elif not estimate_valid:
        deny = "estimate_invalid"
    elif not budget_valid:
        deny = "budget_denied"
    elif not credential_valid:
        deny = "credential_missing"
    elif not provider_route_valid:
        deny = "provider_route_invalid"
    elif not provider_health_allowed:
        deny = "provider_health_denied"

    # Intentional dry OR any security gate failed → effective dry.
    # Live only when caller asked for live AND every gate passed.
    effective_dry = bool(requested_dry_run) or deny is not None
    reported_deny = deny if (not requested_dry_run and deny is not None) else None

    fingerprint = compute_authorization_fingerprint(
        {
            "environment": env,
            "private_lab_enabled": bool(private_lab_enabled),
            "live_probe_enabled": bool(live_probe_enabled),
            "allow_network": bool(allow_network),
            "requested_dry_run": bool(requested_dry_run),
            "effective_dry_run": bool(effective_dry),
            "consent_valid": bool(consent_valid),
            "estimate_valid": bool(estimate_valid),
            "budget_valid": bool(budget_valid),
            "credential_valid": bool(credential_valid),
            "cancellation_requested": bool(cancellation_requested),
            "provider_route_valid": bool(provider_route_valid),
            "provider_health_allowed": bool(provider_health_allowed),
            "deny_reason": reported_deny,
        }
    )
    return ProviderExecutionAuthorization(
        environment=env,
        private_lab_enabled=bool(private_lab_enabled),
        live_probe_enabled=bool(live_probe_enabled),
        allow_network=bool(allow_network),
        requested_dry_run=bool(requested_dry_run),
        effective_dry_run=bool(effective_dry),
        consent_valid=bool(consent_valid),
        estimate_valid=bool(estimate_valid),
        budget_valid=bool(budget_valid),
        credential_valid=bool(credential_valid),
        cancellation_requested=bool(cancellation_requested),
        provider_route_valid=bool(provider_route_valid),
        provider_health_allowed=bool(provider_health_allowed),
        deny_reason=reported_deny,
        authorization_fingerprint=fingerprint,
    )


def compute_runtime_allow_network(
    *,
    environment: str,
    lab_enabled: bool,
    live_probe_enabled: bool,
) -> bool:
    """Runtime-level allow_network — never default True; Probe+Lab+non-prod only."""

    env = str(environment or "").strip().lower()
    if env == "production":
        return False
    if env not in {"development", "test", "dev"}:
        return False
    if not lab_enabled:
        return False
    if not live_probe_enabled:
        return False
    return True


__all__ = [
    "ProviderExecutionAuthorization",
    "compute_authorization_fingerprint",
    "compute_provider_execution_authorization",
    "compute_runtime_allow_network",
]
