# Phase 2A Mock Executor Contract

## Protocol `MockWholeBookRunExecutor`

start, execute_next_stage, execute_until_blocked, pause, resume, retry_stage, cancel, recover, get_execution_state

## Execution model

Single-process, local, deterministic, non-production, testable, recoverable.

## Forbidden

Celery, Redis, distributed tasks, cloud queues, multi-machine scheduling.

## Lab-only test hooks

stage_delay, fail_at_stage, interrupt_at_stage, pause_at_stage, budget_denied_at_stage, synthetic_output_profile

Hooks must NOT appear on formal Engine Protocol.
