# Phase 2A Audit Implementation

Change: `CHG-20260723-034`
Service: `MockRunAuditSink`
Module: `apps/api/app/narrative_core/services/mock_run_audit.py`

## Sink

In-memory records + optional structured logger (`storylens.mock_run_audit`).
`NO_NEW_AUDIT_TABLE = True`.

## Event catalog

`run_created`, `run_started`, `stage_started`, `stage_completed`, `stage_failed`, `pause_requested`, `paused`, `resumed`, `retry_requested`, `cancel_requested`, `cancelled`, `interrupted`, `recovery_planned`, `recovery_rejected`, `run_completed`, `budget_denied`

## Required fields

`event_id`, `run_id`, `event_type`, `previous_state`, `new_state`, `stage_key`, `attempt`, `actor`, `mock`, `non_production`, `idempotency_key`, `occurred_at`, `detail_code`

## Forbidden content

Rejects payload keys / tokens: `full_text`, `novel_body`, `api_key`, `credential`, `system_prompt`, `evidence_full_text`, `prompt`.
