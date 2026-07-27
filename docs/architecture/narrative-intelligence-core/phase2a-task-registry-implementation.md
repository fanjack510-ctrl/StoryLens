# Phase 2A Task Registry Implementation

## Class

`InProcessMockRunTaskRegistry` — `apps/api/app/narrative_core/services/in_process_mock_run_task_registry.py`

## Methods

`register`, `get`, `list`, `request_pause`, `request_cancel`, `mark_finished`, `remove_finished`, `recover_unfinished`

Plus helpers: `mark_running`, `is_pause_requested`, `is_cancel_requested`, `request_cooperative_interrupt_all`

## Rules

1. One `run_id` → one unfinished Task handle
2. Register idempotent
3. Memory holds handles only
4. Database holds factual run/stage state
5. No Task object serialization to DB
6. Shutdown → cooperative interrupt/cancel request
7. Finished handles may be removed
8. Restart does not rely on memory for facts (`recover_unfinished` returns in-memory unfinished ids only)
9. Explicit `non_production=True`
10. No Celery / Redis / queue
