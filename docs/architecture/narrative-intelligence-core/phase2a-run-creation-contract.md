# Phase 2A Run Creation Contract

## Request

`CreateMockWholeBookRunRequest`: book_id, book_snapshot_id, analysis_mode, requested_modules, configuration_fingerprint, idempotency_key, mock_profile, requested_by, preflight_fingerprint.

Must not include full novel body keys.

## Result

`CreateMockWholeBookRunResult`: run_id, book_id, book_snapshot_id, status, analysis_mode, requested_modules, resolved_modules, stage_plan, mock, non_production, created, duplicate_of_run_id, created_at.

## Pre-create checks (fail → no Run/Stage/Artifact/Asset/Engine)

authorize → book → snapshot exists/belongs/completed → preflight fresh → mode/modules/deps → mock engine → idempotency → concurrency → no active conflict → no full body → do not create snapshot.

## Creation sequence

authorize → validate snapshot → validate request → resolve modules → build stage plan → reserve mock slot → create AnalysisRun → create AnalysisRunStages → register execution task → return run view.

## Persistence (no new tables)

Reuse analysis_runs (+ stages/artifacts/assets/relations/conflicts). Mock metadata via existing JSON: subject_type=book, run_scope=whole_book, mock=true, non_production=true, source=mock_lab, engine_id/version, fingerprints.
Schema: `mock_whole_book_run_metadata` / `1.0.0`.
