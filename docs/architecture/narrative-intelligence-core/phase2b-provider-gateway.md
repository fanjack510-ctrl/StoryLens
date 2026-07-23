# Phase 2B Provider Gateway

## WholeBookProviderGateway methods

`validate_policy(...)` · `estimate(...)` · `execute(...)` · `cancel(...)` · `health_check(...)` · `normalize_usage(...)`

## ProviderInferenceRequest

`request_id`, `provider_kind`, `model_route`, `task_type`, `system_instruction_ref`, `prompt_pack_ref`, `input_bundle_ref`, `response_schema_ref`, `temperature_policy`, `token_budget`, `cost_budget`, `timeout_policy`, `retry_policy`, `cancellation_ref`, `data_handling_policy`, `metadata`

Instruction and source_data are isolated (`system_instruction_ref` vs `input_bundle_ref`). No credential fields.

## ProviderInferenceResponse

`request_id`, `provider_kind`, `model_id`, `provider_request_id`, `status`, `structured_output`, `token_input`, `token_output`, `cost`, `latency_ms`, `finish_reason`, `retry_count`, `validation_status`, `received_at`

## Rules

1. Modules do not call providers directly
2. API keys only via existing Provider Credential Service
3. Credentials never enter Request DTO
4. Raw provider response never goes to frontend
5. Raw provider response never becomes Asset
6. Schema Validator required before acceptance
7. Retry under BudgetGuard
8. Cancel must propagate
9. Provider failure must not be forged as success
10. Tests use Fake Provider

No external tools/network requests from the model.
