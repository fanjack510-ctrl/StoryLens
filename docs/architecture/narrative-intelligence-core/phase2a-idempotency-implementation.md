# Phase 2A Idempotency Implementation

Change: `CHG-20260723-034`
Service: `MockRunIdempotencyService`
Module: `apps/api/app/narrative_core/services/mock_run_idempotency.py`

## Store

- Schema: `mock_run_idempotency_store` / version `1.0.0`
- Process-local only (no new table / migration)
- Keys namespaced by `(namespace, actor, request_scope, key)`
- Payload stored as SHA-256 fingerprint only (no novel body)

## APIs

- `register_create_request` / `resolve_create_request`
- `register_operation` / `resolve_operation`
- `mark_operation_completed` / `mark_operation_failed`
- Helpers: `remember_stage_completion`, `remember_artifact_write`, `remember_asset_version_write`

## Namespaces

`create`, `pause`, `resume`, `cancel`, `retry`, `stage_complete`, `artifact_write`, `asset_version_write`

## Rules enforced

1. Same key + same payload → same result
2. Same key + different payload → `MOCK_RUN_IDEMPOTENCY_CONFLICT`
3. Duplicate create does not invent a second run id
4. Duplicate operations replay completed result
5. Duplicate stage completion / artifact / asset version writes are detected

## Schema Issue

`AnalysisRun` has no `metadata_json` column. Durable idempotency cannot be persisted without migration. Optional bind via `client_request_id` (`mock_lab:...`). See `SCHEMA_ISSUE_NO_RUN_METADATA_JSON`.
