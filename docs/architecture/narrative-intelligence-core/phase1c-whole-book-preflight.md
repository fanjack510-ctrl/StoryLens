# Phase 1C Whole-Book Preflight (Read-Only)

## Endpoint

`POST /api/v1/books/{book_id}/whole-book-runs/preflight`

## Semantics

Checks only. **Never**:

- create AnalysisRun / AnalysisRunStage
- create Snapshot
- call Mock Engine `execute_stage`
- call models
- reserve Quota / Budget
- write Asset / Relation / Artifact / Conflict

May read existing Snapshot status. Missing snapshot → check result only (no create).

## Request body

- `analysis_mode` (required)
- `requested_modules` (optional)
- `book_snapshot_id` (optional, check-only)
- `configuration_fingerprint` (optional preview)

## Response (production defaults)

- `run_creation_enabled=false`
- `blocking_reasons` includes at least:
  - `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
  - `whole_book_analysis shipped=false`
  - `no production Engine`
- `engine_status.mock_reported_as_production=false`
- informational `stage_plan` (catalog / plan builder; not executed)

Implementation: `whole_book_preflight.py` + router `whole_book_preflight.py`.
