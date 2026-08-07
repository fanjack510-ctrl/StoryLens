# MEDIUM_PAUSE_RESUME — CHG-20260807-055

DATE：2026-08-07

## Method

1. Formal create with `execute_pipeline=False`.
2. Run extraction with real Gateway window transport.
3. After **≥1** successful Provider Unit，request soft pause **before claiming the next unit**（product `request_pause_whole_book_run_v1` + `should_stop_claiming_units`）.
4. Hold briefly；attempt continue while paused.
5. Resume；finish shared formal pipeline.

Note：Pause is **not** issued mid-`transport.invoke` under an open SQLite write transaction（Gateway + uncommitted orchestrator writes）. Barrier is between units, matching soft-pause contract（in-flight completes；no new units after barrier）.

## Results

| Field | Value |
|---|---|
| CALLS AT PAUSE REQUEST | 1 |
| IN FLIGHT AT PAUSE | 0 |
| COMPLETED AT PAUSE | 1 |
| NEW UNITS STARTED AFTER PAUSE BARRIER | **0** |
| RUN STATUS AFTER SEGMENT | paused |
| RESUME | YES |
| DUPLICATE PROVIDER CALLS | 0 |
| DUPLICATE PROVIDER UNITS | 0 |
| DUPLICATE SUCCESS ASSETS | 0 |
| CONFIRMED OVERWRITE | 0 |

## Verdict

| | |
|---|---|
| PAUSE | **PASS** |
| RESUME | **PASS** |
