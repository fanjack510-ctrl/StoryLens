# Phase 1C Quota Contract

Quota metadata attaches to capabilities via `QuotaPolicy` / `QuotaDecision`.

## Policy kinds (`QuotaPolicyKind`)

`none`, `per_book`, `per_day`, `concurrent_runs`, `character_limit`, `token_budget`, `cost_budget`.

## Whole-book defaults (registry)

`whole_book_analysis` ships with:

- `per_book` — one active run per book snapshot
- `concurrent_runs` — limit 1

## Service hooks

`CapabilityService.evaluate_quota`, `reserve_usage`, `release_usage`, `commit_usage` — Agent H implements.

Cost class (`CostClass`): `free`, `low`, `medium`, `high` on `CapabilityMetadata.estimated_cost_class`.

Phase 1C-P: Protocol + registry metadata only; no live quota persistence.
