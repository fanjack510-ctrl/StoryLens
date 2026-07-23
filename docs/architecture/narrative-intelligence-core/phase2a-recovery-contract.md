# Phase 2A Recovery Contract

## `MockRunRecoveryService`

scan_recoverable_runs, mark_process_interrupted, validate_checkpoint, build_resume_plan, resume_recoverable_run, reject_unrecoverable_run

## Startup

running Stage/Run → interrupted; completed stages stay; checkpoint retained. No silent auto-continue consuming resources.

## Pre-resume checks

Mock Lab run; snapshot exists+completed; engine id/version compatible; configuration_fingerprint match; checkpoint schema/version compatible; completed outputs exist; no duplicate asset write; no canonical overwrite; Lab still enabled.

If Lab disabled: mark interrupted only; do not auto-resume.

Resume requires explicit user click or test call.
