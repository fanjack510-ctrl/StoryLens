# Phase 2A Run Controls Implementation

## Module

`apps/desktop/src/features/wholeBook/runShell/controls/MockRunControls.tsx`

## Actions

| Action | Gate | Notes |
|--------|------|-------|
| Pause | `allowed_actions` includes `pause` | Busy guard; operation idempotency key |
| Resume | `resume` + paused/interrupted | Same `run_id`; completed stages not re-run by client |
| Retry | failed stage selected | Shows downstream impact; no “rerun all” |
| Cancel | secondary confirm | Reminds candidates retained; no Book/Snapshot/file delete |

## Failure policy

On any control failure: present stable error → **re-fetch** `client.get(run_id)` → apply backend view. Never force local status transitions.

Idempotency helpers: `createOperationIdempotencyKey`, `createMockRunIdempotencyKey` (stable per user confirm epoch).
