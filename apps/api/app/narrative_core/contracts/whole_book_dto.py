"""WholeBook request DTOs and validation helpers (Phase 1C-P freeze).

DTOs must NOT hold full novel body text. Engine reads body via SnapshotReader.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.narrative_core.contracts.capability import CapabilityDecision
from app.narrative_core.contracts.stage import WholeBookStagePlan
from app.narrative_core.enums import (
    CapabilityKey,
    SnapshotStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode


@dataclass(frozen=True, slots=True)
class WholeBookAnalysisRequest:
    """Shape for preflight / future run creation — metadata only."""

    book_id: int
    book_snapshot_id: int
    analysis_mode: WholeBookAnalysisMode
    capability_context: CapabilityDecision
    run_id: int | None = None
    requested_modules: tuple[WholeBookModuleKey | str, ...] = ()
    stage_plan: WholeBookStagePlan | None = None
    configuration_fingerprint: str = ""
    provider_policy: dict[str, Any] = field(default_factory=dict)
    budget_context: dict[str, Any] = field(default_factory=dict)
    resume_context: dict[str, Any] = field(default_factory=dict)
    requested_by: str = "user"
    snapshot_status: SnapshotStatus = SnapshotStatus.COMPLETED
    extra: dict[str, Any] = field(default_factory=dict)


def validate_request_shape(request: WholeBookAnalysisRequest) -> None:
    """Validate WholeBook request without touching License or book text."""

    if request.book_id <= 0:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
            "book_id must be positive",
        )
    if request.book_snapshot_id <= 0:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED,
            "book_snapshot_id is required",
        )
    if request.snapshot_status != SnapshotStatus.COMPLETED:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED,
            "snapshot must be COMPLETED",
        )
    if request.analysis_mode not in (
        WholeBookAnalysisMode.NATIVE,
        WholeBookAnalysisMode.ENHANCED,
    ):
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_MODE_NOT_SUPPORTED,
            f"unsupported analysis_mode: {request.analysis_mode}",
        )
    if request.capability_context.capability_key != CapabilityKey.WHOLE_BOOK_ANALYSIS:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
            "capability_context must be whole_book_analysis",
        )
    if not request.capability_context.allowed:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
            request.capability_context.display_message or "capability denied",
        )


def require_consistency_fields(
    *,
    run_id: int | None,
    book_id: int,
    book_snapshot_id: int,
    bound_book_id: int | None = None,
    bound_snapshot_id: int | None = None,
) -> None:
    """Validate Run / Book / Snapshot consistency for future run creation."""

    if bound_book_id is not None and int(bound_book_id) != int(book_id):
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
            f"run book_id {bound_book_id} != request book_id {book_id}",
        )
    if bound_snapshot_id is not None and int(bound_snapshot_id) != int(book_snapshot_id):
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_RUN_SNAPSHOT_MISMATCH,
            (
                f"run snapshot {bound_snapshot_id} != request snapshot "
                f"{book_snapshot_id}"
            ),
        )
    if run_id is not None and run_id <= 0:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
            "run_id must be positive when provided",
        )
