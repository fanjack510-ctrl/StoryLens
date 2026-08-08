# Post-run Usage Accounting

Parsed from usage when present (nullable if absent — never fabricated):
- prompt_tokens / completion_tokens / total_tokens
- prompt_cache_hit_tokens / prompt_cache_miss_tokens
- completion_tokens_details.reasoning_tokens (telemetry only; not analysis text)

Aggregator: provider_usage_accounting.aggregate_estimated_actual_cost_cny
Field name: estimated_actual_cost_cny (NOT actual_billed_cost)
