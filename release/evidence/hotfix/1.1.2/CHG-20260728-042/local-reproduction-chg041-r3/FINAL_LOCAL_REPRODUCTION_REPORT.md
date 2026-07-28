# FINAL LOCAL REPRODUCTION REPORT — CHG-042

## Summary

Frozen CHG-041 R3 Manual Gate DB shows Journey Run 2 (and current Run 3) fail
deterministically under Smoke Fake with:

`JOURNEY_REPAIR_VALIDATION_FAILED`

after `JOURNEY_EVIDENCE_OUT_OF_SCENE` → structural repair → `JOURNEY_SCENE_ID_MISMATCH`.

CHG-041 routing/confirm remains tested; Manual Gate stays FAILED because Journey
Fake fixture cannot complete a 4-scene journey, and UI still maps failed→paused
plus ~8h elapsed skew.

## Minimal fixes (for later implementation — not done here)

### Minimal core fix

1. Smoke Fake: per-scene `evidence_paragraph_ids` must be subset of that scene’s
   paragraph IDs (never shared global `paragraph_ids[:2]`).
2. Smoke Fake repair: emit **all** expected scene_ids from the repair request.
3. Optional: serialize journey timestamps with explicit `Z`/offset.

### Minimal UI fix

1. Sidebar: Journey `failed` → failed/paused-accurate copy (not `partial`「分析已暂停」).
2. `journeyElapsedMs`: parse naive timestamps as UTC (reuse `parseAnalysisTimestamp`).

## Status

- Production code modified: **NO**
- Ready for implementation prompt: **YES**
- Database migration required: **NO**
