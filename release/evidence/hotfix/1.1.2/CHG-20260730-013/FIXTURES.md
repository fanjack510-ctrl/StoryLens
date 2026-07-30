# FIXTURES — CHG-20260730-013

## A. Confirm + Delayed Worker

- Seed: AI candidates 6 → manually edit to 3 → Confirm+Start
- Inject: hold/delay BackgroundTasks or Worker claim ≥5s (test harness patches `BackgroundTasks.add_task`)
- Assert UI/API: `workflow_state=starting`; recover does not set `JOURNEY_INTERRUPTED`

## B. Recoverable Interrupted

- Seed: journey claimed + stale → boot recover marks interrupted
- Action: Continue once
- Assert: same `analysis_run_id` / `journey_run_id`; route = current journey; reservations/new runs = 0

## Accident DB replay

- Read-only copy: `D:\StoryLensIncident\INC-20260730-006-confirm-start-journey-race\database\`
- Formal writes: 0
- Replay intent: reopen isolated copy; Continue once should re-arm starting without scene-review dead end (covered by service + HTTP resume idempotency tests)
