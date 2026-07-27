# Phase 2A Run State Machine

Statuses: pending, running, paused, interrupted, completed, failed, cancelled.

## Legal transitions

- pending → running | cancelled
- running → paused | interrupted | completed | failed | cancelled
- paused → running | cancelled
- interrupted → running | cancelled | failed
- failed → running | cancelled
- completed terminal
- cancelled terminal

## Rules

1. illegal jumps forbidden
2. completed cannot resume
3. cancelled cannot resume
4. failed re-enters running only via retry/resume policy (product action: retry)
5. every transition carries expected_state or expected_version
6. transitions idempotent
7. frontend must not mutate status
8. Run status aggregated by backend service / stages

Active set (concurrency): pending, running, paused, interrupted. failed does not occupy slot by default.
