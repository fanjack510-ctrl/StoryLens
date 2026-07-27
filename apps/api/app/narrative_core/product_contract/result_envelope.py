"""Unified whole-book result envelope (Phase 1D-P).

Frontend must consume Envelope + typed module payload — never raw model JSON.
Envelope must not store full novel body text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.product_contract.enums import WholeBookModuleStatus

RESULT_ENVELOPE_SCHEMA = "whole_book_result_envelope"
RESULT_ENVELOPE_VERSION = "1"


@dataclass(frozen=True, slots=True)
class ConfidenceSummaryDto:
    mean: float | None = None
    min: float | None = None
    max: float | None = None
    labeled_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReviewSummaryDto:
    candidate_count: int = 0
    confirmed_count: int = 0
    corrected_count: int = 0
    rejected_count: int = 0
    locked_count: int = 0
    conflict_count: int = 0


@dataclass(frozen=True, slots=True)
class WholeBookResultEnvelope:
    schema: str
    version: str
    run_id: int
    book_id: int
    book_snapshot_id: int
    analysis_mode: WholeBookAnalysisMode
    module_key: WholeBookModuleKey
    module_status: WholeBookModuleStatus
    generated_at: str
    source_stage_keys: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]
    asset_ids: tuple[int, ...]
    asset_version_ids: tuple[int, ...]
    relation_ids: tuple[int, ...]
    relation_version_ids: tuple[int, ...]
    conflict_ids: tuple[int, ...]
    evidence_count: int
    confidence_summary: ConfidenceSummaryDto
    review_summary: ReviewSummaryDto
    stale: bool
    partial: bool
    warnings: tuple[str, ...]
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.schema:
            raise ValueError("schema is required")
        if not self.version:
            raise ValueError("version is required")
        if "full_text" in self.payload or "body" in self.payload:
            raise ValueError("payload must not embed full novel body")
        # stale ≠ failed; conflict ≠ failed — status may combine flags
        if self.module_status == WholeBookModuleStatus.FAILED and self.stale:
            # allowed but discouraged; keep as warning only via callers
            pass
