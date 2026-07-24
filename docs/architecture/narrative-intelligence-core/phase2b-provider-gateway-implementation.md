# Phase 2B Provider Gateway Implementation

`DefaultWholeBookProviderGateway` with:

- `FakeProviderAdapter`
- `ProviderAdapterRegistry`
- Policy validation / Estimate / Execute / Cancel / Health / Usage normalize

## Rules

- Modules call Gateway only
- No Bailian / OpenAI / llama-server / DeepSeek / Qwen HTTP in this phase
- Credential resolve separated from Request DTO
- Raw provider responses never returned to frontend
- Structured output validated
- Retry under BudgetGuard
- Cancel propagates
- Failures are not forged as success
- Usage marked `synthetic=true`
