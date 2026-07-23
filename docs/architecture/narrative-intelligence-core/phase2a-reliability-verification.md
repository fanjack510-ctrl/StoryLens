# Phase 2A Reliability Verification

Change: `CHG-20260723-034`
Tests: `apps/api/tests/test_narrative_phase2a_recovery.py`

## Directed command

```bash
python -m pytest apps/api/tests/test_narrative_phase2a_recovery.py -q
```

Do **not** run full pytest suite for this Change.

## Coverage map

| # | Case |
|---|------|
| 1 | Create idempotency |
| 2 | Payload conflict |
| 3–7 | Operation idempotency (pause/resume/cancel/retry) |
| 8–10 | Duplicate stage / artifact / asset version |
| 11–14 | Book conflict, single executor, reserve/release, failed slot |
| 15–18 | Scan / interrupt / completed preserved / resume plan |
| 19–25 | Lab disabled, snapshot, engine, config, schema, corrupt |
| 26–27 | Audit events + no body |
| 28–33 | Quota limits + budget deny no asset |
| 34–38 | Fault fail/interrupt, registry loss, restart, no silent resume |
| 39–41 | version_manager check, change_registry check, git diff --check |

## Integration Issues

1. Shared `apps/api/app/main.py` still uses `mark_interrupted_runs_failed` only — wire `MockRunStartupRecoveryAdapter` in CHG-035.
2. Schema Issue: no `AnalysisRun.metadata_json` for durable idempotency (process-local store for Phase 2A).
3. Agent M Mock Run Service not present on this branch; recovery services are standalone for Integration merge.
