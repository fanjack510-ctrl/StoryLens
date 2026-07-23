"""HTTP-facing DTO skeletons for Phase 1C capability / whole-book APIs.

POST /whole-book-runs is DISABLED in Phase 1C-P — DTO-only freeze; no live router.
"""

from __future__ import annotations

from dataclasses import dataclass
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
class WholeBookPreflightDTO:
    """Future preflight response — not wired to production routes in Phase 1C-P."""

    book_id: int
    book_snapshot_id: int
    analysis_mode: WholeBookAnalysisMode
    capability: CapabilityDecisionDTO
    engine_id: str | None = None
    stage_count: int = 0
    notes: dict[str, Any] | None = None
