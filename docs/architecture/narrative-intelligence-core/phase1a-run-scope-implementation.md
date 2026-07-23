# Phase 1A — Run Scope Implementation (Agent B)

**Change:** CHG-20260723-013  
**Branch:** `feature/narrative-phase1a-runstage`  
**Worktree:** `D:\Dstorylens-wt-narrative-runstage`  
**Baseline:** Phase 1P `e983e7279d4c72655334017da114ce572e41b0e0`

## Modules

| Module | Role |
|--------|------|
| `apps/api/app/narrative_core/services/run_scope_service.py` | `create_scoped_run` / `validate_run_scope` / `bind_run_snapshot` |
| `apps/api/app/narrative_core/services/run_stage_service.py` | Facade implementing `AnalysisRunService` Protocol (composes scope) |
| Migrations `20260723_004_analysis_run_scope` | Owned by Agent B; SQL frozen in Phase 1P runner (no DDL fork this Change) |

## Scope rules

### CHAPTER

- Binds via existing `subject_type` / `subject_id` (no `chapter_id` column).
- Does **not** require Book Snapshot.
- Rejects `start_chapter_id` / `end_chapter_id` (conflict with chapter scope).

### CHAPTER_RANGE

- Requires `book_id`, `start_chapter_id`, `end_chapter_id`.
- Start `chapter_index` must not exceed end.
- Both chapters must belong to the same book and match `book_id`.
- Snapshot **not** required (Phase 1P Contract).

### BOOK

- Requires `book_id`.
- Requires COMPLETED Snapshot via `SnapshotValidationGateway` only.
- Snapshot must belong to the same book.
- BUILDING / FAILED / INVALID snapshots rejected by gateway (`SNAPSHOT_NOT_COMPLETED` / mismatch codes).
- Creates **simulated** runs (`task_type=whole_book_simulated`); no model execution.

## analysis_type compatibility

- `scene_pipeline` (legacy chapter)
- `whole_book_native`
- `whole_book_enhanced`
- Legacy rows with `analysis_type=NULL` + `subject_type=chapter` remain valid under `validate_run_scope`.

## Snapshot gateway usage

Agent B injects `SnapshotValidationGateway` into `RunScopeService` / `RunStageService`.

Methods used:

- `get_completed_snapshot(snapshot_id)`
- `validate_snapshot_for_book(snapshot_id, book_id)`

Test stub: `StubSnapshotValidationGateway` (reads `BookSnapshot` rows only; does not build snapshots).

## Compatibility facts preserved

1. 1.0.5 `AnalysisRun` has no `chapter_id`.
2. Old chapter binding remains `subject_type` / `subject_id`.
3. No forged `chapter_id`.
4. Old runs with NULL scope fields continue to load and validate.
