"""Effective execution mode resolution (local / cloud / hybrid).

Separates routing mode from analysis quality profile (FAST/BALANCED/QUALITY).
"""

from __future__ import annotations

from typing import Literal

ExecutionMode = Literal["local", "cloud", "hybrid"]

_VALID: frozenset[str] = frozenset({"local", "cloud", "hybrid"})


def normalize_execution_mode(raw: str | None) -> ExecutionMode | None:
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if not value:
        return None
    if value in _VALID:
        return value  # type: ignore[return-value]
    return None


def resolve_effective_execution_mode(
    *,
    provider_is_cloud: bool,
    cloud_enabled: bool,
    configured_execution_mode: str | None = None,
    local_provider_available: bool = False,
) -> ExecutionMode:
    """Resolve the mode that create-run / routers must honor.

    Rules:
    - Cloud providers never resolve to ``local`` when cloud is enabled
      (including missing / stale ``local`` defaults from older installs).
    - Explicit ``hybrid`` is kept only when a local provider is available.
    - Local providers resolve to ``local`` (hybrid/cloud requests are caller errors).
    - Cloud provider with cloud disabled still returns ``cloud`` so callers can
      raise a clear switch/eligibility error instead of CLOUD_MODE_REQUIRED.
    """

    configured = normalize_execution_mode(configured_execution_mode)

    if provider_is_cloud:
        if configured == "hybrid" and local_provider_available and cloud_enabled:
            return "hybrid"
        if configured == "cloud":
            return "cloud"
        # missing / empty / stale local → cloud when using a cloud provider
        if cloud_enabled or configured in {None, "local"}:
            return "cloud"
        return "cloud"

    if configured == "hybrid" and local_provider_available:
        return "hybrid"
    return "local"


def cloud_enabled_from_session(session) -> bool:
    """Read ApplicationSetting cloud_enabled; default False when absent."""

    import json

    from app.db.models import ApplicationSetting

    row = session.get(ApplicationSetting, "cloud_enabled")
    if row is None or not row.value_json:
        return False
    try:
        return bool(json.loads(row.value_json))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


__all__ = [
    "ExecutionMode",
    "cloud_enabled_from_session",
    "normalize_execution_mode",
    "resolve_effective_execution_mode",
]
