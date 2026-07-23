# Phase 2A Task Registry Contract

## `InProcessMockRunTaskRegistry`

register, get, list, request_pause, request_cancel, mark_finished, remove_finished, recover_unfinished

## Rules

1. process-local handles only
2. DB is factual source of truth
3. restart must not rely on memory for facts
4. unfinished runs recover via DB + checkpoint
5. one run_id → one execution task
6. register idempotent
7. shutdown marks running stage interrupted
8. do not serialize Task objects to DB
9. no new background service dependency
10. non-production
