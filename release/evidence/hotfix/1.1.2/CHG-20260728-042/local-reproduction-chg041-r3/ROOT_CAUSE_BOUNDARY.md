# CHG-042 Root Cause Boundary (post Round 4 fixture repair)

## LOCAL REPRO ROOT CAUSE

**confirmed**

Category: `FAKE_FIXTURE_INVALID`

Local CHG-041 Round 3 Manual Gate Journey failure
(`JOURNEY_REPAIR_VALIDATION_FAILED`) is explained by Smoke Fake:

1. Batch Fake reused out-of-scene evidence (`P0001` on Scene 2+)
2. Structural Repair Fake returned incomplete expected IDs (`[1]` for `[1,2]`)

Round 4 repairs the Fake success fixture for Manual Gate retest.
That does **not** prove the same root cause for production.

## PRODUCTION INCIDENT ROOT CAUSE

**unconfirmed**

INC-20260728-003 / production copies of `JOURNEY_REPAIR_VALIDATION_FAILED`
are still **not** confirmed to share `FAKE_FIXTURE_INVALID`.

Still required before any production core fix:

- Desensitized diagnostic JSON from an affected machine, **or**
- A complete sanitized incident copy with real Provider traces

## CHG-042 STATUS

**investigated**

## READY FOR PRODUCTION CORE FIX

**NO**

## Explicit non-claims

- Do **not** mark CHG-042 `resolved` or `fixed`
- Do **not** treat Round 4 Fake fixture repair as production incident closure
- Do **not** equate local Fake repro with online Provider/schema root cause
