# Phase 2A Metadata & Idempotency Boundary

**Change:** CHG-20260723-035
**Module:** `apps/api/app/narrative_core/services/mock_run_metadata.py`

## Storage (no migrations)

Mock run metadata lives in existing `AnalysisRun.validated_output` JSON. No new columns or migrations.

## Nested envelope

Integration standardizes a nested key:

```text
validated_output.mock_whole_book_run_metadata → { schema, version, book_id, ... }
```

Other `validated_output` keys (e.g. future result stubs) are preserved on merge writes. Schema/version required; silent field drop forbidden.

Required metadata flags include `mock`, `non_production`, `source`, `engine_id`, idempotency fields, and configuration fingerprint.

## Create idempotency (durable via metadata)

- Client supplies `idempotency_key` + payload hash
- On successful create, key and hash persist in metadata envelope
- Replay with same key + hash returns existing run (HTTP 200)
- Same key + different payload → conflict error

Create idempotency survives process restart because it is stored in DB JSON.

## Operation idempotency (process-local limitation)

Pause/resume/cancel/retry operation keys are deduped in `MockRunIdempotencyService` in-memory store. **Not durable across process restart.** After restart, duplicate operation POST may re-execute unless guarded by run state machine.

Documented limitation — no new tables in Phase 2A.

## Structural output dedupe

Completed stage artifacts are not re-written on resume: executor skips stages already `completed`; checkpoint validation binds resume to last consistent stage. Prevents duplicate asset rows for the same stage attempt.

## Integration resolution

Agent O noted "Schema Issue: no metadata_json column." Integration resolves by using `validated_output` nested envelope (`METADATA_SCHEMA_SUFFICIENT=true`). No migration required for Phase 2A Lab scope.
