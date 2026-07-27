# Phase 2A Mock Quota Implementation

Change: `CHG-20260723-034`
Services: `MockExecutionQuotaService`, `MockExecutionBudgetGuard`
Module: `apps/api/app/narrative_core/services/mock_execution_quota.py`

## Policy (synthetic / non-production)

Uses `MockExecutionQuotaPolicy` defaults from Phase 2A-P:

- concurrent mock runs
- max mock chapters / characters
- max synthetic tokens / cost
- max run duration

## Semantics

1. Not commercial billing; not License; separate from Cloud Budget
2. `persist_across_restart = False` (restart clears memory)
3. `reserve` / `commit` / `release` idempotent
4. Over-limit releases concurrency slot when guard is wired
5. Budget deny never writes assets (`write_assets_on_deny=False`)

## Test injection

Construct `MockExecutionQuotaPolicy(...)` with lower limits; optional `deny_at_stage` on `MockExecutionBudgetGuard`.
