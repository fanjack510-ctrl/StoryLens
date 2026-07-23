"""Narrative Intelligence Core shared contracts (Phase 1P).

Agents A/B/C implement against these modules; do not fork enums or protocols.
"""

from app.narrative_core.enums import (
    AnalysisScopeType,
    AnalysisType,
    SnapshotStatus,
    StageStatus,
)
from app.narrative_core.errors import NarrativeCoreErrorCode
from app.narrative_core.hash_canon import calculate_text_hash, canonicalize_text
from app.narrative_core.stage_transitions import (
    ALLOWED_STAGE_TRANSITIONS,
    is_allowed_stage_transition,
)

__all__ = [
    "AnalysisScopeType",
    "AnalysisType",
    "SnapshotStatus",
    "StageStatus",
    "NarrativeCoreErrorCode",
    "canonicalize_text",
    "calculate_text_hash",
    "ALLOWED_STAGE_TRANSITIONS",
    "is_allowed_stage_transition",
]
