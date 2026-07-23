# Phase 2A Fault Injection

Change: `CHG-20260723-034`
Module: `apps/api/app/narrative_core/services/mock_run_fault_injection.py`

## Profile kinds

- `fail_at_stage`
- `interrupt_at_stage`
- `pause_at_stage`
- `budget_denied_at_stage`
- `corrupted_checkpoint`
- `engine_version_mismatch`
- `duplicate_stage_completion`
- `duplicate_asset_write`
- `task_registry_loss`
- `process_restart_marker`

## Constraints

1. Test/dev only (`assert_fault_injection_allowed`)
2. Production / `STORYLENS_PRODUCTION` forbidden
3. Never written to formal config
4. Deterministic fingerprint
5. No model calls
6. No real Book data pollution

## Usage

`FaultInjectionController` applies outcomes for reliability tests and recovery/idempotency verification. Agent M executor may consume the same profile shape via Lab hooks.
