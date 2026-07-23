# Phase 2A Polling Implementation

## Module

`apps/desktop/src/features/wholeBook/runShell/polling/mockRunPollingController.ts`
Hook: `useMockRunPolling.ts`

## Policy (DEFAULT_MOCK_RUN_POLLING_POLICY)

| State | Interval |
|-------|----------|
| running / pending | 1500ms |
| paused / interrupted | 4000ms |
| completed / failed / cancelled | stop |
| page hidden | max(base, 10000ms) |

Floor: **≥ 1000ms** (no high-frequency polling). No WebSocket.

## Behaviors

1. Consecutive errors → exponential backoff; after `max_consecutive_errors` stop polling.
2. Network error **does not** mark Run `failed` (previous snapshot retained).
3. Stale responses discarded via `updated_at` / `version` (`discardStalePollResponse`).
4. Switching `run_id` cancels prior schedule (generation bump).
5. `dispose` / unmount stops timers; **does not** call cancel API.
6. Frontend close ≠ backend cancel.
