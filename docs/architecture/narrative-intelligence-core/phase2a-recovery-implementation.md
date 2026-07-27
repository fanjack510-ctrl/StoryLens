# Phase 2A Recovery Implementation

Change: `CHG-20260723-034`
Service: `MockRunRecoveryService`
Module: `apps/api/app/narrative_core/services/mock_run_recovery_service.py`

## Methods

- `scan_recoverable_runs`
- `mark_process_interrupted`
- `validate_checkpoint`
- `build_resume_plan`
- `resume_recoverable_run`
- `reject_unrecoverable_run`

## Startup behavior

`MockRunStartupRecoveryAdapter.reconcile()`:

1. Scan recoverable mock lab runs
2. Mark running run/stage → `interrupted`
3. Preserve completed stages + checkpoints
4. **Never** auto-resume
5. **Never** start tasks or consume synthetic budget

## Explicit resume

`allow_explicit_resume(True)` must be set by user click or test before `resume_recoverable_run`.

## Lab disabled

Mark interrupted only; resume rejected with `MOCK_LAB_DISABLED`.

## Phase 1A compatibility

Runs without stages are soft-interrupted without inventing stage rows.

## Reuse

AnalysisRun / AnalysisRunStage, BookSnapshot, Phase 1C Mock Engine IDs, Phase 2A-P recovery contract. No second Run Service.
