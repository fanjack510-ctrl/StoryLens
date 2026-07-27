# Phase 1C Engine ↔ Asset Boundary

Separates WholeBook engine execution from narrative foundation storage.

## Foundation (NOT Pro-gated)

- Entity / alias CRUD
- Asset / version / evidence storage
- Relation / evidence storage
- Conflict recording

Capability key: `narrative_asset_library` — `is_pro_gated_capability()` returns **false**.

## Pro-gated execution

- Whole-book analysis **runs** (`whole_book_analysis`)
- Stage outputs may **write** candidates via `NarrativeAssetWriter` / `NarrativeRelationWriter` Protocols
- Engine uses `SnapshotReader` — metadata + completed snapshot id, never full book in DTO

## I/O Protocols

`engine_io.py`: `SnapshotReader`, `NarrativeAssetWriter`, `NarrativeRelationWriter`, `ArtifactWriter`, `BudgetGuard`, `CancellationToken`; reuse `AnalysisConflictSink` from `conflict.py`.

Agent G implements writers against Phase 1B services without modifying contract files.
