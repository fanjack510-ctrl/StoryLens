# Phase 2A Mock Executor Implementation

## Class

`DefaultMockWholeBookRunExecutor` — `apps/api/app/narrative_core/services/mock_whole_book_run_executor.py`

Implements `MockWholeBookRunExecutor` Protocol:

`start`, `execute_next_stage`, `execute_until_blocked`, `pause`, `resume`, `retry_stage`, `cancel`, `recover`, `get_execution_state`

## Wiring

- `MockWholeBookAnalysisEngine`
- `WholeBookStageOrchestrator`
- `RunStageService`
- `ArtifactWriterAdapter` / `NarrativeAssetWriterAdapter` / `NarrativeRelationWriterAdapter`
- `BudgetGuardAdapter` / `CancellationTokenImpl`

## Rules enforced

- Single-process, local, deterministic, non-production
- Completed stages not re-run
- Cooperative pause; cancel checked before/after stage
- Checkpoint carries schema/version
- BudgetGuard before writes (hooks + engine path)
- Stage artifacts marked mock/synthetic/non-production
- Candidates only — no confirm / lock / canonical
- No model calls

## Lab-only test hooks

`stage_delay_ms`, `fail_at_stage`, `interrupt_at_stage`, `pause_at_stage`, `budget_denied_at_stage`, `synthetic_output_profile`

Forbidden on formal Engine Protocol. `recover()` only marks interrupted (no silent auto-resume; Agent O owns recovery core).
