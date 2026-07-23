"""Protocol contracts for Narrative Intelligence Core (Phase 1P).

Implementations belong to Agent A (ledger/hash/snapshot) and Agent B (run/stage).
"""

from app.narrative_core.contracts.hash import ContentHashService
from app.narrative_core.contracts.migration_ledger import MigrationLedger
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
]
