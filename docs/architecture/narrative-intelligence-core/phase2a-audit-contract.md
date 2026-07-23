# Phase 2A Audit Contract

## Event fields

event_id, run_id, event_type, previous_state, new_state, stage_key, attempt, actor, mock, non_production, idempotency_key, occurred_at, detail_code

## Sinks allowed now

Run/Stage metadata, structured logs, test Audit Sink.

## Forbidden

New formal audit DB table; logging full book body / API key / credential / full prompt / evidence full text.
