# Phase 1P Contract Verification

**Change:** CHG-20260723-011  
**Date:** 2026-07-23  

## Schema creation

- [x] ORM models: `SchemaMigration`, `BookSnapshot`, `BookSnapshotChapter`, `BookSnapshotParagraph`, `AnalysisRunStage`
- [x] Chapter/Paragraph `content_hash` nullable columns
- [x] AnalysisRun additive scope fields (nullable)
- [x] `create_all` + `apply_narrative_phase1p_migrations` on temp SQLite

## Enums / contracts

- [x] `AnalysisScopeType`, `SnapshotStatus`, `StageStatus`, `AnalysisType`
- [x] Protocols under `app.narrative_core.contracts`
- [x] Stage transition matrix importable
- [x] Error codes frozen

## Migration order

Frozen IDs `20260723_001` … `20260723_005` + `baseline_1_0_5`. Unique ID test present.

## Compatibility

- [x] Simulated 1.0.5 `analysis_runs` row survives upgrade
- [x] New scope columns nullable / NULL on legacy rows
- [x] No VERSION bump

## Tests run

See final report section F. Primary: `pytest apps/api/tests/test_narrative_phase1p_contract.py`.

## Not verified in 1P (deferred)

- Full Snapshot service transactions  
- Run stage pause/resume business loop  
- Production DB upgrade (copy-only later)  
- Frontend Pattern Map UI  
