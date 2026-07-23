"""Protocol contracts for Narrative Intelligence Core (Phase 1P + Phase 1B-P + Phase 1C-P).

Phase 1A: Agent A (ledger/hash/snapshot), Agent B (run/stage).
Phase 1B: Agent D (entity), Agent E (asset), Agent F (relation/conflict).
Phase 1C-P: Engine / Capability / Quota contracts (Agents G/H/I parallel).
"""

from app.narrative_core.contracts.api_dto import (
    CapabilityDecisionDTO,
    CapabilityListItemDTO,
    WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
    WholeBookPreflightDTO,
)
from app.narrative_core.contracts.asset import NarrativeAssetService
from app.narrative_core.contracts.capability import (
    CapabilityDecision,
    CapabilityMetadata,
    CapabilityService,
    NARRATIVE_FOUNDATION_CAPABILITY_KEYS,
    QuotaDecision,
    QuotaPolicy,
    evaluate_from_metadata,
    is_pro_gated_capability,
)
from app.narrative_core.contracts.conflict import AnalysisConflictService, AnalysisConflictSink
from app.narrative_core.contracts.engine import (
    WholeBookAnalysisEngine,
    WholeBookEngineFactory,
    WholeBookEngineRegistry,
)
from app.narrative_core.contracts.engine_io import (
    ArtifactWriter,
    BudgetGuard,
    CancellationToken,
    NarrativeAssetWriter,
    NarrativeRelationWriter,
    SnapshotReader,
)
from app.narrative_core.contracts.entity import NarrativeEntityService
from app.narrative_core.contracts.evidence import __all__ as evidence_exports
from app.narrative_core.contracts.hash import ContentHashService
from app.narrative_core.contracts.migration_ledger import MigrationLedger
from app.narrative_core.contracts.quota import __all__ as quota_exports
from app.narrative_core.contracts.relation import NarrativeRelationService
from app.narrative_core.contracts.run import AnalysisRunService, AnalysisRunStageRepository
from app.narrative_core.contracts.snapshot import (
    BookSnapshotRepository,
    BookSnapshotService,
    SnapshotValidationGateway,
)
from app.narrative_core.contracts.stage import (
    WholeBookStageContext,
    WholeBookStageDefinition,
    WholeBookStagePlan,
    WholeBookStageResult,
)
from app.narrative_core.contracts.whole_book_dto import (
    WholeBookAnalysisRequest,
    require_consistency_fields,
    validate_request_shape,
)

__all__ = [
    "MigrationLedger",
    "ContentHashService",
    "BookSnapshotRepository",
    "BookSnapshotService",
    "SnapshotValidationGateway",
    "AnalysisRunService",
    "AnalysisRunStageRepository",
    "NarrativeEntityService",
    "NarrativeAssetService",
    "NarrativeRelationService",
    "AnalysisConflictService",
    "AnalysisConflictSink",
    "CapabilityMetadata",
    "CapabilityDecision",
    "CapabilityService",
    "QuotaPolicy",
    "QuotaDecision",
    "evaluate_from_metadata",
    "is_pro_gated_capability",
    "NARRATIVE_FOUNDATION_CAPABILITY_KEYS",
    "WholeBookAnalysisEngine",
    "WholeBookEngineFactory",
    "WholeBookEngineRegistry",
    "WholeBookStageDefinition",
    "WholeBookStagePlan",
    "WholeBookStageContext",
    "WholeBookStageResult",
    "WholeBookAnalysisRequest",
    "validate_request_shape",
    "require_consistency_fields",
    "SnapshotReader",
    "NarrativeAssetWriter",
    "NarrativeRelationWriter",
    "ArtifactWriter",
    "BudgetGuard",
    "CancellationToken",
    "CapabilityListItemDTO",
    "CapabilityDecisionDTO",
    "WholeBookPreflightDTO",
    "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED",
    *evidence_exports,
    *quota_exports,
]
