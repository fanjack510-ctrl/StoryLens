"""HTTP-facing DTO skeletons for Phase 1C capability / whole-book APIs.

POST /whole-book-runs create remains DISABLED — WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=True.
Preflight is read-only (Integration): checks only, never creates Run/Snapshot/Assets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.narrative_core.enums import (
    CapabilityAvailability,
    CapabilityKey,
    CapabilityReasonCode,
    WholeBookAnalysisMode,
)

WHOLE_BOOK_RUNS_ENDPOINT_DISABLED = True


@dataclass(frozen=True, slots=True)
class CapabilityListItemDTO:
    key: CapabilityKey
    label: str
    description: str
    shipped: bool
    availability: CapabilityAvailability
    requires_license: bool


@dataclass(frozen=True, slots=True)
class CapabilityDecisionDTO:
    capability_key: CapabilityKey
    allowed: bool
    reason_code: CapabilityReasonCode
    availability: CapabilityAvailability
    message: str = ""
    preview_only: bool = False


@dataclass(frozen=True, slots=True)
class WholeBookPreflightRequestDTO:
    """Read-only preflight input — never triggers run creation."""

    analysis_mode: WholeBookAnalysisMode
    requested_modules: tuple[str, ...] = ()
    book_snapshot_id: int | None = None
    configuration_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class WholeBookPreflightDTO:
    """Transport DTO — backend HTTP Preflight response (Phase 1C / 1D).

    Data-of-record for preflight facts. Does **not** carry page-only derived
    fields (those belong on WholeBookPreflightPageModel after Mapper).
    Always returns run_creation_enabled=False under production defaults.
    """

    book_id: int
    analysis_mode: WholeBookAnalysisMode
    capability: CapabilityDecisionDTO
    book_snapshot_id: int | None = None
    snapshot_status: str | None = None
    chapter_count: int = 0
    character_count: int = 0
    requested_mode: str = ""
    supported_modules: tuple[str, ...] = ()
    stage_plan: tuple[dict[str, Any], ...] = ()
    capability_decision: dict[str, Any] = field(default_factory=dict)
    quota_decision: dict[str, Any] = field(default_factory=dict)
    engine_status: dict[str, Any] = field(default_factory=dict)
    run_creation_enabled: bool = False
    blocking_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    engine_id: str | None = None
    stage_count: int = 0
    notes: dict[str, Any] | None = None


# Frozen Transport DTO name (Phase 1D Integration). Same shape as WholeBookPreflightDTO.
WholeBookPreflightResponseDto = WholeBookPreflightDTO