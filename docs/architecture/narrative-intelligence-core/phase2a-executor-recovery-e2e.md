# Phase 2A Executor, Recovery & E2E

**Change:** CHG-20260723-035
**Tests:** `apps/api/tests/test_narrative_phase2a_integration.py`

## Ten stages

Mock whole-book executor runs the frozen `ORDERED_STAGE_KEYS` pipeline (10 stages):

1. `build_fulltext_index`
2. `resolve_entities`
3. `analyze_structure`
4. `analyze_storylines`
5. `analyze_characters`
6. `analyze_hooks`
7. `analyze_causality_timeline`
8. `generate_diagnostics`
9. `verify_evidence`
10. `persist_narrative_assets`

Each stage writes checkpoint JSON (schema `mock_whole_book_checkpoint` / version `1`) and optional stage artifacts. Completed stages are not re-run on resume.

## Checkpoint validation

`CheckpointValidator` verifies schema/version, run/stage IDs, stage key, attempt, engine id/version, configuration fingerprint, snapshot binding, integrity hash, and resumability before explicit resume proceeds.

## Startup reconcile (no silent resume)

`MockRunStartupRecoveryAdapter.reconcile()` runs in `main.py` lifespan when Lab is enabled:

- Scans non-terminal mock runs
- Marks interrupted runs as `interrupted` (or equivalent terminal-safe state)
- **Does not** auto-start executors
- **Does not** set `explicit_resume_allowed`

Shared `mark_interrupted_runs_failed` for legacy analysis runs remains separate.

## Explicit resume only

`MockRunRecoveryService` gates resume on `explicit_resume_allowed=True`, set only by user action path (Lab API resume / test hook). Startup path leaves this false. Resume validates checkpoint then delegates to executor; completed stages skipped.

## E2E scenarios (integration test matrix)

| Test | Scenario |
|------|----------|
| `test_complete_mock_run_e2e` | Create → start → 10 stages → completed → result projection |
| `test_pause_resume_completed_stages_not_rerun` | Pause mid-run; resume skips completed |
| `test_failure_retry_partial_results_retained` | Stage failure → retry; partial artifacts kept |
| `test_cancel_retains_candidates_and_book_snapshot` | Cancel preserves candidates + snapshot |
| `test_restart_recovery_no_silent_resume_no_duplicate_artifacts` | Simulated restart → interrupted; explicit resume; no dup writes |

Security, OpenAPI, metadata, and runtime composition tests cover the remaining integration acceptance surface.
