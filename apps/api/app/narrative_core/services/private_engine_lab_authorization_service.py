"""Private Engine Lab authorization service (Phase 2B-R Agent S).

Fail-closed gate for development/test Private Engine Lab only.
Distinct from Mock Lab. Does not mutate Capability metadata, License, or ship flags.
"""

from __future__ import annotations

import os
from typing import Any

from app.narrative_core.run_shell_contract.private_engine_lab import (
    ALLOWED_PRIVATE_ENGINE_LAB_ENVIRONMENTS,
    PRIVATE_ENGINE_LAB_DENY_MESSAGES,
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER,
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_VALUE,
    PRIVATE_PROVIDER_LIVE_PROBE_ENV,
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
    PrivateEngineLabAuthorizationDecision,
    PrivateEngineLabAuthorizationInput,
    PrivateEngineLabDenyReason,
    evaluate_private_engine_lab_authorization,
)
from app.narrative_core.services.mock_lab_authorization_service import is_loopback_host

# Env var name — default closed unless explicitly true.
PRIVATE_ENGINE_LAB_ENABLED_ENV = "WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED"


def is_private_engine_lab_enabled_from_env(
    *,
    environ: dict[str, str] | None = None,
    default: bool = WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get(PRIVATE_ENGINE_LAB_ENABLED_ENV, "")).strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


def is_private_provider_live_probe_enabled(
    *,
    environ: dict[str, str] | None = None,
) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get(PRIVATE_PROVIDER_LIVE_PROBE_ENV, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def private_engine_lab_request_marker_present(headers: Any) -> bool:
    if headers is None:
        return False
    try:
        raw = headers.get(PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER)
        if raw is None:
            raw = headers.get(PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER.lower())
    except Exception:  # noqa: BLE001 — defensive for Mapping / Headers
        return False
    return str(raw or "").strip() == PRIVATE_ENGINE_LAB_REQUEST_MARKER_VALUE


class PrivateEngineLabAuthorizationDenied(Exception):
    """Raised when Private Engine Lab authorization fails."""

    def __init__(
        self,
        reason: PrivateEngineLabDenyReason,
        *,
        message: str | None = None,
    ) -> None:
        self.reason = reason
        self.message = message or PRIVATE_ENGINE_LAB_DENY_MESSAGES[reason]
        super().__init__(self.message)


class PrivateEngineLabAuthorizationService:
    """evaluate / require Private Engine Lab authorization without formal License bypass."""

    def __init__(
        self,
        *,
        environment: str | None = None,
        lab_enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        self._environ = environ
        if environment is not None:
            self._environment = str(environment)
        else:
            env = environ if environ is not None else os.environ
            self._environment = str(
                env.get("STORYLENS_APP_ENV")
                or env.get("APP_ENV")
                or env.get("ENVIRONMENT")
                or "development"
            ).strip().lower()
        if lab_enabled is not None:
            self._lab_enabled = bool(lab_enabled)
        else:
            self._lab_enabled = is_private_engine_lab_enabled_from_env(environ=environ)

    @property
    def environment(self) -> str:
        return self._environment

    @property
    def lab_enabled(self) -> bool:
        return self._lab_enabled

    def evaluate(
        self,
        *,
        loopback: bool,
        request_marker_present: bool,
        credential_present: bool = False,
        data_transfer_consented: bool = False,
        budget_ok: bool = True,
        capability_ok: bool = True,
        user_confirmed: bool = False,
        non_production: bool = True,
        dry_run: bool = True,
    ) -> PrivateEngineLabAuthorizationDecision:
        return evaluate_private_engine_lab_authorization(
            PrivateEngineLabAuthorizationInput(
                environment=self._environment,
                loopback=bool(loopback),
                lab_enabled=self._lab_enabled,
                request_marker_present=bool(request_marker_present),
                credential_present=bool(credential_present),
                data_transfer_consented=bool(data_transfer_consented),
                budget_ok=bool(budget_ok),
                capability_ok=bool(capability_ok),
                user_confirmed=bool(user_confirmed),
                non_production=bool(non_production),
                dry_run=bool(dry_run),
            )
        )

    def require(
        self,
        *,
        loopback: bool,
        request_marker_present: bool,
        credential_present: bool = False,
        data_transfer_consented: bool = False,
        budget_ok: bool = True,
        capability_ok: bool = True,
        user_confirmed: bool = False,
        non_production: bool = True,
        dry_run: bool = True,
    ) -> PrivateEngineLabAuthorizationDecision:
        decision = self.evaluate(
            loopback=loopback,
            request_marker_present=request_marker_present,
            credential_present=credential_present,
            data_transfer_consented=data_transfer_consented,
            budget_ok=budget_ok,
            capability_ok=capability_ok,
            user_confirmed=user_confirmed,
            non_production=non_production,
            dry_run=dry_run,
        )
        if not decision.allowed:
            reason = PrivateEngineLabDenyReason(
                decision.reason_code or PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_DISABLED.value
            )
            raise PrivateEngineLabAuthorizationDenied(reason)
        return decision

    def assert_environment_allowed(self) -> None:
        if self._environment not in ALLOWED_PRIVATE_ENGINE_LAB_ENVIRONMENTS:
            raise PrivateEngineLabAuthorizationDenied(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_ENVIRONMENT_NOT_ALLOWED
            )


def should_register_private_engine_lab_router(
    *,
    environment: str,
    lab_enabled: bool,
) -> bool:
    """Private Engine Lab router mounts only when env is development/test AND Lab is enabled."""
    env = str(environment or "").strip().lower()
    if env == "production":
        return False
    if env not in ALLOWED_PRIVATE_ENGINE_LAB_ENVIRONMENTS:
        return False
    return bool(lab_enabled)


__all__ = [
    "PRIVATE_ENGINE_LAB_ENABLED_ENV",
    "PrivateEngineLabAuthorizationDenied",
    "PrivateEngineLabAuthorizationService",
    "is_loopback_host",
    "is_private_engine_lab_enabled_from_env",
    "is_private_provider_live_probe_enabled",
    "private_engine_lab_request_marker_present",
    "should_register_private_engine_lab_router",
]
