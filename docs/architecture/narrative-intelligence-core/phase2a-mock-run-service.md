# Phase 2A Mock Run Service

## Class

`MockWholeBookRunService` — `apps/api/app/narrative_core/services/mock_whole_book_run_service.py`

## Methods

`create_run`, `get_run`, `get_run_stages`, `pause_run`, `resume_run`, `cancel_run`, `retry_stage`

## Create sequence (frozen)

authorize → validate snapshot → validate request → resolve modules → build stage plan → reserve mock slot → create AnalysisRun → create AnalysisRunStages → register execution task → return run view

Pre-create failure: no Run / Stage / Artifact / Asset / Engine execute.

## Persistence

- Reuses `analysis_runs` + `analysis_run_stages`
- Mock metadata in `validated_output` JSON (`mock_whole_book_run_metadata` / `1.0.0`)
- Idempotency via `client_request_id` + payload hash
- No new columns / migrations
- `METADATA_SCHEMA_SUFFICIENT=true` (no Schema Issue)

## Concurrency

Default one active Mock Run per book (`pending|running|paused|interrupted`).

## Authorization

Delegates to `MockLabAuthorizationService.evaluate/require` (env ∈ {development,test}, Lab flag, loopback, marker, mock engine, non_production). Does not mutate Capability / License / ship flags.
