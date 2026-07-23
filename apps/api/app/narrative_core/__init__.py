"""Narrative Intelligence Core shared contracts (Phase 1P / Phase 1A).

Agents A/B/C implement against these modules; do not fork enums or protocols.
"""

from app.narrative_core.enums import (
    AnalysisScopeType,
    AnalysisType,
    RunStatus,
    SnapshotStatus,
    StageStatus,
)
from app.narrative_core.errors import NarrativeCoreErrorCode
from app.narrative_core.hash_canon import (
    BookHashChapterInput,
    calculate_book_content_hash,
    calculate_text_hash,
    canonicalize_text,
)
from app.narrative_core.stage_transitions import (
    ALLOWED_STAGE_TRANSITIONS,
    is_allowed_stage_transition,
)

__all__ = [
    "AnalysisScopeType",
    "AnalysisType",
    "RunStatus",
    "SnapshotStatus",
    "StageStatus",
    "NarrativeCoreErrorCode",
    "BookHashChapterInput",
    "canonicalize_text",
    "calculate_text_hash",
    "calculate_book_content_hash",
    "ALLOWED_STAGE_TRANSITIONS",
    "is_allowed_stage_transition",
]
