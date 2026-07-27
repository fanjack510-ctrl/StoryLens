# Phase 2B-R Provider and Budget Plan

**Change:** CHG-20260723-041  
**Source audit commit:** `737617f2576a49c94d539e665484a4cdba55a6a5`  
**Live Provider calls this phase:** forbidden

## 1. Existing real Providers (code)

From `apps/api/app/model_gateway/registry.py` + `apps/api/app/core/config.py`:

| Provider key | Default model | Notes |
|--------------|---------------|-------|
| `aliyun_qwen_plus` | `qwen3.7-plus` | Primary supported cloud path; connection test; scene analysis flags |
| `aliyun_qwen_max` | `qwen3.7-max` | `manual_only=True` |
| `aliyun_qwen_flash` | `qwen3.6-flash` | `manual_only=True` |
| `local_llama` | `qwen-local` | `enabled=False`, `manual_only=True` |
| Local profiles | from `config/local_model_profiles.yaml` | OpenAI-compatible to `local_llama_base_url` default `http://127.0.0.1:8080/v1` |

Whole-book gateway today: `DefaultWholeBookProviderGateway` + `FakeProviderAdapter` only (`_NETWORK_FORBIDDEN=True` in `whole_book_provider_gateway.py`).

## 2. First real whole-book Provider path

**Choice:** `aliyun_qwen_plus` / model `qwen3.7-plus` / QualityProfile `balanced`.

Selection criteria met in code:

1. Credential + connection test (`/api/v1/model-providers/aliyun_qwen_plus/test`)  
2. Budget + cost (`cloud_budget.py`, `cloud_pricing.default.json`)  
3. Structured output (`json_object`)  
4. Long-text context bootstrap `32768` tokens  
5. Cancel/timeout/retry knobs exist on chapter path (`aliyun_timeout_seconds=300`, transport retry settings)  
6. User-facing BYOK already productized  
7. Minimal delta: adapt existing `OpenAICompatibleProvider` behind `ProviderAdapter`  
8. Testable with Fake + recorded fixtures before live  
9. Credential stays in public Gateway execute boundary — **not** in private module DTO  
10. Modules never HTTP  

## 3. QualityProfile → Model Route (planned)

Axes remain separate (`private_engine_contract/quality.py`): AnalysisMode ≠ QualityProfile ≠ ModelRoute.

| QualityProfileKey | provider_policy_key (contract) | Planned provider_key | Planned model_id | Context note |
|-------------------|--------------------------------|----------------------|------------------|--------------|
| `fast` | `policy.fast` | `aliyun_qwen_flash` | `qwen3.6-flash` | Enable only after capability/product allows non-manual |
| `balanced` | `policy.balanced` | `aliyun_qwen_plus` | `qwen3.7-plus` | **2B-R first route** |
| `high_quality` | `policy.high_quality` | `aliyun_qwen_max` | `qwen3.7-max` | Second wave; higher unit price in pricing JSON |
| `custom` | user/policy | explicit route only | explicit | Must still go through Gateway |

Routing strategy tables live in **private** repo; public side stores only Manifest refs + fingerprint inputs.

## 4. Endpoint / credential / structured output

| Item | Source of truth |
|------|-----------------|
| Endpoint | `resolve_aliyun_compatible_base_url` in `apps/api/app/services/aliyun_endpoint.py` |
| Public Beijing default | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Credential | `CredentialStore.get("aliyun_qwen_plus")` via `ExistingCredentialServiceAdapter` (enable for real Lab only) |
| FORBIDDEN in Request DTO | Keys in `FORBIDDEN_PROVIDER_REQUEST_KEYS` (`provider_gateway.py` contract) |
| Structured mode | Settings `aliyun_structured_output_mode=json_object` |

## 5. Budget wiring plan

| Layer | Existing | 2B-R plan |
|-------|----------|-----------|
| Protocol | `BudgetGuard` (`contracts/engine_io.py`) | Keep |
| Mock | `BudgetGuardAdapter`, `MockExecutionBudgetGuard` | Do not reuse as “real analysis done” signal |
| Chapter cloud | `cloud_budget.py` daily request/token/cost | Reuse for Private Lab real calls |
| Defaults | requests 50 / tokens 200000 / cost 1.0 | Surface in consent UI; fingerprint policy version |
| Per-run | `run_scoped_budget_auth.py` | Optional inflate only with explicit user auth |
| Estimate vs actual | `WholeBookUsageEstimate` / `WholeBookUsageActual` | Keep separated; no commercial SKU in module DTO |

Stop immediately on budget deny; keep validated partial candidates already persisted.

## 6. Retry / cancel / timeout

| Concern | Plan |
|---------|------|
| Timeout | Start from `aliyun_timeout_seconds=300`; version in fingerprint |
| Transport retry | Reuse `transport_retry_policy_from_settings` bounds; no infinite retry |
| Cancel | `ProviderAdapter.cancel` + `CancellationTokenImpl`; Lab must expose cancel |
| Schema repair retry | Private Engine only; bounded attempts; never forge success |

## 7. Agent ownership

| Agent | Provider-related ownership |
|-------|----------------------------|
| **S** | Real `ProviderAdapter` for Bailian; Credential enablement for Lab; budget bridge; Private Lab gates; no module algorithms |
| **T** | Consumes Gateway Protocol only; no HTTP; no credential fields |
| **Integration** | Wire adapter into composition root; E2E with Fake then Private Lab |

## 8. This phase verification

Static proof only: no HTTP to dashscope/maas; gateway `_NETWORK_FORBIDDEN` remains True on HEAD until Agent S flips under Private Lab flag (not in CHG-041).
