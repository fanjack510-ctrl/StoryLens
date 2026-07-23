# Phase 2B Quality & Model Routing

Three distinct axes — never collapse into one enum.

| Axis | Values / owner |
|------|----------------|
| **Analysis Mode** | `whole_book_native`, `whole_book_enhanced` |
| **Quality Profile** | `fast`, `balanced`, `high_quality`, `custom` |
| **Model Route** | Decided by Provider Policy |

## WholeBookQualityProfile fields

`profile_key`, `provider_policy_key`, `context_strategy_key`, `retry_policy_key`, `evidence_policy_key`, `budget_policy_key`, `quality_expectation`, `user_visible`, `custom`

## Rules

- Profile does not expose internal prompts
- Profile does not hardcode commercial prices
- Model ID may update via Provider Policy
- Configuration fingerprint includes Profile
- No per-novel automatic special Profile switch
