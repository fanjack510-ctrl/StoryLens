# Phase 2B Budget & Usage

Reuses BudgetGuard, Provider Budget, Capability Quota. No new billing tables; formal commercial quota is later. Real production Runs remain disabled.

## Real analysis usage fields

`context_characters`, `context_tokens_estimated`, `provider_input_tokens`, `provider_output_tokens`, `cached_tokens`, `provider_cost`, `retries`, `module_usage`, `stage_usage`

## Rules

1. Estimate vs actual kept separate
2. Synthetic vs real cost kept separate
3. Check budget before each Provider call
4. Re-check before retry
5. Budget denied → no Candidate write
6. Partial results may be retained
7. Internal cost routing not exposed as commercial price
8. No new billing DB tables
9. Formal commercial Quota deferred
10. Real Run still closed
