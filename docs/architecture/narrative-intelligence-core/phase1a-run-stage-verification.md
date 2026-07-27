# Phase 1A — Run Stage Verification (Agent B)

**Change:** CHG-20260723-013  
**Date:** 2026-07-23

## Commands run

```text
D:\Dstorylens\.venv\Scripts\python.exe -m pytest ^
  apps/api/tests/test_narrative_run_scope.py ^
  apps/api/tests/test_narrative_run_stage.py -q

python scripts/version_manager.py check
python scripts/change_registry.py check
git diff --check
```

Full pytest suite / publish / build: **not** run (out of Agent B scope).

## Coverage checklist

| # | Case | Result |
|---|------|--------|
| 1 | Legacy chapter run readable | PASS |
| 2 | Old subject_type/subject_id compat | PASS |
| 3 | Chapter scope validation | PASS |
| 4 | Range missing bounds fails | PASS |
| 5 | Range order invalid fails | PASS |
| 6 | Range chapters not same book fails | PASS |
| 7 | Book scope without snapshot fails | PASS |
| 8 | Snapshot not completed fails | PASS |
| 9 | Snapshot book mismatch fails | PASS |
| 10 | Initialize stages idempotent | PASS |
| 11 | Duplicate stage_key fails | PASS |
| 12 | Legal transitions | PASS |
| 13 | Illegal transitions | PASS |
| 14 | Completed cannot retry | PASS |
| 15 | Failed retry increments attempt_count | PASS |
| 16 | Pause does not write failed | PASS |
| 17 | Resume skips completed | PASS |
| 18 | Interrupted handling | PASS |
| 19 | Checkpoint schema/version | PASS |
| 20 | Token/cost accumulate | PASS |
| 21 | FK / integrity columns present | PASS |
| 22 | version_manager check | (recorded at commit time) |
| 23 | change_registry check | (recorded at commit time) |
| 24 | git diff --check | (recorded at commit time) |

## Integration Issues filed

1. **II-RUNSTAGE-001 — Startup `mark_interrupted_runs_failed` vs Stage `interrupted`**  
   Existing `app.services.scene_pipeline.mark_interrupted_runs_failed` permanently marks `AnalysisRun` rows `failed` on sidecar restart. Phase 1A `mark_interrupted` keeps stage/run semantics as interruptible (not permanent failure). Agent B must not rewrite global startup behavior; Integration should reconcile.

2. **II-RUNSTAGE-002 — SnapshotValidationGateway stub until Agent A lands**  
   Tests use `StubSnapshotValidationGateway` reading `BookSnapshot` rows. Production wiring must inject Agent A’s real gateway after merge; do not fork snapshot builders in Agent B.

3. **II-RUNSTAGE-003 — Run-level status vocabulary**  
   Stage statuses are frozen; run-level `paused` / `interrupted` reuse `AnalysisRun.status` string field without a full task-system refactor. Integration may later map these onto a dedicated run state machine.

## Non-goals verified absent

- No Snapshot service implementation  
- No Hash / Migration Ledger changes  
- No models.py edits  
- No whole-book prompts / engines  
- No Narrative Asset / Reader Journey / Scene / Hook / Pro / frontend / VERSION changes  
- No build / publish / push  
