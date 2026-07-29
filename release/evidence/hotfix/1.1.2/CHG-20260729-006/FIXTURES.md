# Fixtures A–D — CHG-20260729-006

## Fixture A — Queued stop

- Status: `queued`
- Action: cancel
- Expect: Provider Calls=0; `cancelled`; reservation released; UI 已停止

Covered by: `test_queued_cancel_becomes_cancelled_without_provider_calls`

## Fixture B — Scene analysis in-flight stop

- 6 scenes; Fake first request blocked conceptually
- Cancel while running → `cancellation_requested` then worker finalize
- Current request may finish; no new provider calls after cancel checkpoint
- Completed scenes retained; Task=`cancelled`

Covered by: running cancel + `raise_if_cancel_requested` / `generate_validated` pre-call check tests

## Fixture C — Paused stop

- `awaiting_provider_recovery` with partial progress
- Cancel finalizes immediately to `cancelled`
- Reanalyze = new task (`can_restart_as_new_task`)

Covered by: `test_awaiting_provider_recovery_cancel_finalizes_immediately`

## Fixture D — Complete race

- Succeed first → cancel returns already_completed; status stays `succeeded`
- Cancel first → worker must not submit `succeeded` (`try_finalize` before succeed)

Covered by: `test_race_succeed_then_cancel_stays_succeeded` + worker succeed gates
