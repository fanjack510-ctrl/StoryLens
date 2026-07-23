"""Service implementations for Narrative Intelligence Core.

Phase 1A: migration ledger, content hash backfill, book snapshot,
run scope, and run stage lifecycle.
Phase 1B Agent D: narrative entity / alias repository and service.
Phase 1B Agent E: narrative asset / version / evidence.
Phase 1B Agent F: relation / evidence / analysis conflict.
"""

from app.narrative_core.services.asset_evidence_service import NarrativeAssetEvidenceService
from app.narrative_core.services.asset_repository import NarrativeAssetRepository
from app.narrative_core.services.asset_service import (
    AssetCanonicalConflictRequest,
    AssetMutationResult,
    NarrativeAssetService,
)
from app.narrative_core.services.conflict_service import (
    AnalysisConflictServiceImpl,
    ConflictCreateRequest,
)
from app.narrative_core.services.conflict_sink import (
    AnalysisConflictSink,
    AnalysisConflictSinkImpl,
    NullAnalysisConflictSink,
)
from app.narrative_core.services.entity_repository import (
    NarrativeEntityRepository,
    normalize_alias_text,
)
from app.narrative_core.services.entity_service import (
    AliasLookupResult,
    EntityMergeResult,
    NarrativeEntityServiceImpl,
)
from app.narrative_core.services.hash_backfill import ContentHashServiceImpl
from app.narrative_core.services.migration_ledger import MigrationLedgerService
from app.narrative_core.services.pattern_projection import (
    PatternProjectionInput,
    build_pattern_projection_input,
)
from app.narrative_core.services.relation_repository import NarrativeRelationRepository
from app.narrative_core.services.relation_service import NarrativeRelationServiceImpl
from app.narrative_core.services.run_scope_service import RunScopeService
from app.narrative_core.services.run_stage_repository import (
    CHECKPOINT_SCHEMA,
    CHECKPOINT_VERSION,
    RunStageRepository,
    validate_checkpoint_payload,
)
from app.narrative_core.services.run_stage_service import RunStageService, SimulatedStageRunner
from app.narrative_core.services.snapshot_repository import BookSnapshotRepositoryImpl
from app.narrative_core.services.snapshot_service import (
    BookSnapshotServiceImpl,
    SnapshotValidationGatewayImpl,
)

__all__ = [
    "MigrationLedgerService",
    "ContentHashServiceImpl",
    "BookSnapshotRepositoryImpl",
    "BookSnapshotServiceImpl",
    "SnapshotValidationGatewayImpl",
    "RunScopeService",
    "RunStageRepository",
    "RunStageService",
    "SimulatedStageRunner",
    "CHECKPOINT_SCHEMA",
    "CHECKPOINT_VERSION",
    "validate_checkpoint_payload",
    "NarrativeEntityRepository",
    "NarrativeEntityServiceImpl",
    "AliasLookupResult",
    "EntityMergeResult",
    "normalize_alias_text",
    "NarrativeAssetRepository",
    "NarrativeAssetService",
    "NarrativeAssetEvidenceService",
    "AssetCanonicalConflictRequest",
    "AssetMutationResult",
    "NarrativeRelationRepository",
    "NarrativeRelationServiceImpl",
    "AnalysisConflictServiceImpl",
    "ConflictCreateRequest",
    "AnalysisConflictSink",
    "AnalysisConflictSinkImpl",
    "NullAnalysisConflictSink",
    "PatternProjectionInput",
    "build_pattern_projection_input",
]

# StubSnapshotValidationGateway / make_stub_completed_snapshot remain importable
# from run_scope_service for tests only — not re-exported as production defaults.
