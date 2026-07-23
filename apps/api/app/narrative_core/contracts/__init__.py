"""Protocol contracts for Narrative Intelligence Core (Phase 1P + Phase 1B-P).

Phase 1A: Agent A (ledger/hash/snapshot), Agent B (run/stage).
Phase 1B: Agent D (entity), Agent E (asset), Agent F (relation/conflict).
"""

from app.narrative_core.contracts.asset import NarrativeAssetService
from app.narrative_core.contracts.conflict import AnalysisConflictService, AnalysisConflictSink
from app.narrative_core.contracts.entity import NarrativeEntityService
from app.narrative_core.contracts.evidence import __all__ as evidence_exports
from app.narrative_core.contracts.hash import ContentHashService
from app.narrative_core.contracts.migration_ledger import MigrationLedger
from app.narrative_core.contracts.relation import NarrativeRelationService
from app.narrative_core.contracts.run import AnalysisRunService, AnalysisRunStageRepository
from app.narrative_core.contracts.snapshot import (
    BookSnapshotRepository,
    BookSnapshotService,
    SnapshotValidationGateway,
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
    *evidence_exports,
]
