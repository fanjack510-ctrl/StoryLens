# Phase 2A Checkpoint Validation

Change: `CHG-20260723-034`
Service: `CheckpointValidator`
Module: `apps/api/app/narrative_core/services/mock_run_recovery_service.py`

## Expected envelope

- schema: `mock_whole_book_checkpoint`
- version: `1.0.0`

## Checked fields

`schema`, `version`, `run_id`, `run_stage_id`, `stage_key`, `attempt`, `engine_id`, `engine_version`, `configuration_fingerprint`, `snapshot_id`, `integrity_hash`, `resumable`

## Failure codes

- `MOCK_RUN_CHECKPOINT_INVALID` (schema/version/corruption/config/stage)
- `MOCK_RUN_ENGINE_VERSION_MISMATCH`
- `MOCK_RUN_SNAPSHOT_INVALID`
- `MOCK_RUN_NOT_RECOVERABLE` (not resumable / missing completed outputs)

## Safety

- Corrupted JSON is never treated as completed
- Body / prompt / credential keys are stripped from builder input
- Error detail codes are stable tokens (no novel body)
