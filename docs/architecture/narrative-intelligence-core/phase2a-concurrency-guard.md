# Phase 2A Concurrency Guard

Change: `CHG-20260723-034`
Service: `MockRunConcurrencyGuard`
Module: `apps/api/app/narrative_core/services/mock_run_idempotency.py`

## Rules

1. Default ≤1 active Mock Run per Book
2. One Executor lease per Run
3. Active = `pending|running|paused|interrupted`
4. `failed` does not occupy slot by default
5. `completed|cancelled` release slot
6. `reserve` / `release` are idempotent
7. Create failure / executor start failure should release via `release_book_slot` / `release_executor`
8. Conflicts use stable codes: `MOCK_RUN_ALREADY_ACTIVE`, `MOCK_RUN_STATE_CONFLICT`
9. In-process only (no Redis / distributed lock)

## Integration note

Agent M Mock Run Service should call `reserve_book_slot` before create and `note_run_status` on every factual status change.
