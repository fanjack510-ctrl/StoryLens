"""Phase 1D-P whole-book product contracts (DTO / state / API shape only).

No real run creation, no model calls, no Pattern ORM tables.
"""

from __future__ import annotations

from app.narrative_core.product_contract.conflict_center import ConflictCenterItemDto
from app.narrative_core.product_contract.evidence import WholeBookEvidenceRefDto
from app.narrative_core.product_contract.keys import (
    MODULE_STAGE_DEPENDENCIES,
    RESULT_NAV_SECTIONS,
    WHOLE_BOOK_MODULE_KEYS,
    resolve_modules_with_dependencies,
)
from app.narrative_core.product_contract.module_results import (
    MODULE_RESULT_DTO_BY_KEY,
    BookOverviewResultV2,
    ClaimStatus,
    CitedBoundaryDto,
    CitedClaimDto,
    CoverageScope,
    StructureStageV2,
    StructureStagesResultV2,
    TurningPointV2,
)
from app.narrative_core.product_contract.preflight import WholeBookPreflightPageModel
from app.narrative_core.product_contract.result_envelope import WholeBookResultEnvelope
from app.narrative_core.product_contract.review import NarrativeReviewActionRequest
from app.narrative_core.product_contract.run_view import (
    WholeBookRunViewState,
    WholeBookStageProgressDto,
)
from app.narrative_core.product_contract.structure_map import (
    NarrativeStructureMapProjectionDto,
)

__all__ = [
    "BookOverviewResultV2",
    "ClaimStatus",
    "CitedBoundaryDto",
    "CitedClaimDto",
    "ConflictCenterItemDto",
    "CoverageScope",
    "MODULE_RESULT_DTO_BY_KEY",
    "MODULE_STAGE_DEPENDENCIES",
    "NarrativeReviewActionRequest",
    "NarrativeStructureMapProjectionDto",
    "RESULT_NAV_SECTIONS",
    "StructureStageV2",
    "StructureStagesResultV2",
    "TurningPointV2",
    "WHOLE_BOOK_MODULE_KEYS",
    "WholeBookEvidenceRefDto",
    "WholeBookPreflightPageModel",
    "WholeBookResultEnvelope",
    "WholeBookRunViewState",
    "WholeBookStageProgressDto",
    "resolve_modules_with_dependencies",
]
