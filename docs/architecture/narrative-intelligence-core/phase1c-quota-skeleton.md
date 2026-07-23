# Phase 1C Quota Skeleton

## Backend

`InMemoryQuotaService` in `apps/api/app/narrative_core/services/quota_service.py`.

- **Backend tag:** `memory_non_production`
- **Not** a payment database
- **Not** cloud_budget / `cloud_budget_reservations` (those remain separate)
- No new SQLite tables in Phase 1C

## Policy kinds

`none`, `per_book`, `per_day`, `concurrent_runs`, `character_limit`, `token_budget`, `cost_budget`

Default whole-book registry policies (frozen metadata):

- `per_book` limit 1
- `concurrent_runs` limit 1

Production evaluations still fail first on `shipped=false` before quota matters.

## API

| Method | Behavior |
|--------|----------|
| `evaluate_quota` | used + reserved vs limit; `reset_at` for per_day / window |
| `reserve_usage` | occupies reserved; message `reserved:<id>` |
| `commit_usage` | reserved → used (except concurrent slot released) |
| `release_usage` | frees reserved; **idempotent** on repeat / unknown id |

Failure paths must `release_usage` (callers). Guard/preflight do not reserve by default.

## Test injection

```python
InMemoryQuotaService(policy_overrides={
  "whole_book_analysis": (QuotaPolicy(kind=QuotaPolicyKind.PER_DAY, limit=2),)
})
```

Must not write into the formal application database.

## Integration stop condition

If durable commercial quota tables are required → stop and file Integration Issue. This phase intentionally stays in-memory.
