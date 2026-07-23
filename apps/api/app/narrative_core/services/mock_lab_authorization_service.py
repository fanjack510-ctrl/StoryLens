"""Mock Lab authorization service (Phase 2A Agent M).

Fail-closed gate for development/test Mock Lab only.
Does not mutate Capability metadata, License, ship flags, or commercial usage.
"""

from __future__ import annotations

import os
from typing import Any

from app.narrative_core.run_shell_contract.errors import MockRunError, MockRunErrorCode, mock_run_error
from app.narrative_core.run_shell_contract.mock_lab import (
    ALLOWED_MOCK_LAB_ENVIRONMENTS,
    MOCK_ENGINE_ID,
    MOCK_LAB_REQUEST_MARKER_HEADER,
    MOCK_LAB_REQUEST_MARKER_VALUE,
    WHOLE_BOOK_MOCK_LAB_ENABLED,
    MockLabAuthorizationDecision,
    MockLabAuthorizationInput,
    evaluate_mock_lab_authorization,
)

# Env var name — default closed unless explicitly true.
MOCK_LAB_ENABLED_ENV = "WHOLE_BOOK_MOCK_LAB_ENABLED"


def is_mock_lab_enabled_from_env(
    *,
    environ: dict[str, str] | None = None,
    default: bool = WHOLE_BOOK_MOCK_LAB_ENABLED,
) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get(MOCK_LAB_ENABLED_ENV, "")).strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


def is_loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    value = host.strip().lower()
    if not value:
        return False
    # Strip port if present (e.g. 127.0.0.1:8000)
    if value.startswith("["):
        # IPv6 [::1]:port
        end = value.find("]")
        value = value[1:end] if end > 0 else value
    else:
        value = value.split("%", 1)[0]
        if ":" in value and value.count(":") == 1:
            # host:port (IPv4)
            value = value.rsplit(":", 1)[0]
    return value in {"127.0.0.1", "localhost", "::1", "testclient"}


def request_marker_present(headers: Any) -> bool:
    if headers is None:
        return False
    try:
        raw = headers.get(MOCK_LAB_REQUEST_MARKER_HEADER)
        if raw is None:
            raw = headers.get(MOCK_LAB_REQUEST_MARKER_HEADER.lower())
    except Exception:  # noqa: BLE001 — defensive for Mapping / Headers
        return False
    return str(raw or "").strip() == MOCK_LAB_REQUEST_MARKER_VALUE


class MockLabAuthorizationService:
    """evaluate / require Lab authorization without formal License bypass."""

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
            self._lab_enabled = is_mock_lab_enabled_from_env(environ=environ)

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
        requested_engine_id: str | None = MOCK_ENGINE_ID,
        engine_is_mock: bool = True,
        engine_non_production: bool = True,
        capability_context_is_lab: bool = True,
        snapshot_completed: bool = True,
        declare_mock_lab: bool = True,
    ) -> MockLabAuthorizationDecision:
        # Explicit mock-lab declaration required (separate from header marker).
        marker_ok = bool(request_marker_present) and bool(declare_mock_lab)
        return evaluate_mock_lab_authorization(
            MockLabAuthorizationInput(
                environment=self._environment,
                loopback=bool(loopback),
                lab_enabled=self._lab_enabled,
                request_marker_present=marker_ok,
                requested_engine_id=requested_engine_id,
                engine_is_mock=bool(engine_is_mock),
                engine_non_production=bool(engine_non_production),
                capability_context_is_lab=bool(capability_context_is_lab),
                snapshot_completed=bool(snapshot_completed),
            )
        )

    def require(
        self,
        *,
        loopback: bool,
        request_marker_present: bool,
        requested_engine_id: str | None = MOCK_ENGINE_ID,
        engine_is_mock: bool = True,
        engine_non_production: bool = True,
        capability_context_is_lab: bool = True,
        snapshot_completed: bool = True,
        declare_mock_lab: bool = True,
    ) -> MockLabAuthorizationDecision:
        decision = self.evaluate(
            loopback=loopback,
            request_marker_present=request_marker_present,
            requested_engine_id=requested_engine_id,
            engine_is_mock=engine_is_mock,
            engine_non_production=engine_non_production,
            capability_context_is_lab=capability_context_is_lab,
            snapshot_completed=snapshot_completed,
            declare_mock_lab=declare_mock_lab,
        )
        if not decision.allowed:
            code = MockRunErrorCode(decision.reason_code or MockRunErrorCode.MOCK_LAB_DISABLED.value)
            raise MockLabAuthorizationDenied(mock_run_error(code))
        return decision

    def assert_environment_allowed(self) -> None:
        if self._environment not in ALLOWED_MOCK_LAB_ENVIRONMENTS:
            raise MockLabAuthorizationDenied(
                mock_run_error(MockRunErrorCode.MOCK_LAB_ENVIRONMENT_NOT_ALLOWED)
            )


class MockLabAuthorizationDenied(Exception):
    """Raised when Lab authorization fails. Carries frozen MockRunError."""

    def __init__(self, error: MockRunError) -> None:
        self.error = error
        super().__init__(error.message)


__all__ = [
    "MOCK_LAB_ENABLED_ENV",
    "MockLabAuthorizationDenied",
    "MockLabAuthorizationService",
    "is_loopback_host",
    "is_mock_lab_enabled_from_env",
    "request_marker_present",
]
