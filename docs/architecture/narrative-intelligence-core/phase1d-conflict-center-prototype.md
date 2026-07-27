# Phase 1D Conflict Center Prototype (Agent L)

Change: `CHG-20260723-029`

## Backend

`apps/api/app/narrative_core/services/conflict_center_service.py`

- Projects `AnalysisConflict` → `ConflictCenterItemDto`
- Compare left/right + Evidence previews (no full body)
- Resolve / dismiss via Review Action Adapter
- Defer is soft UI state (conflict stays `open`)
- `BLOCKING_CONFLICTS_AUTO_RESOLVE_FORBIDDEN = True`

## Frontend

`apps/desktop/src/features/wholeBook/review/ConflictCenter.tsx`

Components: `ConflictCenterList`, `ConflictCenterItem`, `ConflictComparisonPanel`, `ConflictEvidenceComparison`, `ConflictResolutionPanel`.

Supports severity/status filters, keep-old / confirm-new / create-corrected / dismiss / defer.

Does not write ORM directly. Not on formal result navigation.
