# L3_REAL_PROVIDER_TEST_PLAN — CHG-20260728-040

**DO NOT EXECUTE without explicit user authorization.**

## Freeze

| Item | Value |
|------|-------|
| Sample | Minimal synthetic Chinese paragraphs producing ≥20 boundary candidates (desensitized; not user novel) |
| Provider | `aliyun_qwen_plus` |
| Model | `qwen3.7-plus` |
| Goal | 20 candidates → 2 batches; initial limit ≠ 768; if length, retry limit increases; full coverage; usage visible |
| Max logical calls | 4 |
| Max actual calls | 6 |
| In-code truncation retry | allowed |
| Operator auto-retry | OFF |
| Cost ceiling | awaiting user approval |
| REAL PROVIDER CALLS this phase | **0** |

## Stop conditions

- Success with complete adjudication, or
- Hard-cap truncation error after ≤3 attempts/batch, or
- Cost/call ceiling reached
