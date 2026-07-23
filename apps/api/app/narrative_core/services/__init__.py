"""Service implementations for Narrative Intelligence Core.

Phase 1A: migration ledger, content hash backfill, book snapshot,
run scope, and run stage lifecycle.
"""

from app.narrative_core.services.hash_backfill import ContentHashServiceImpl
from app.narrative_core.services.migration_ledger import MigrationLedgerService
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
]

# StubSnapshotValidationGateway / make_stub_completed_snapshot remain importable
# from run_scope_service for tests only — not re-exported as production defaults.
