# Phase 2B-R1 Provider Payload & Estimate

**Change:** CHG-20260723-045 (plan) → implement CHG-046 (Agent U)

## 1. Forbid ref-only live payload

Current (`BailianOpenAICompatibleProviderAdapter._execute_live`):

```text
system: instruction_ref={request.system_instruction_ref}
user:   input_bundle_ref={request.input_bundle_ref}
```

This is **not** Live-ready. R1 must replace with resolved Provider messages.

## 2. Public Protocol: `ProviderInputBundleResolver`

Suggested location (new):  
`apps/api/app/narrative_core/private_engine_contract/provider_input.py`  
and/or service Protocol in `services/` with Fake under public tree.

Methods:

| Method | Purpose |
|--------|---------|
| `resolve(...)` | Build ephemeral Provider Input Bundle (messages + metadata); body not persisted |
| `estimate(...)` | Token/cost estimate without side effects |
| `build_transfer_manifest(...)` | `WholeBookDataTransferManifest` (no body/key/prompt/raw) |
| `validate_consent(...)` | Consent fingerprint vs Manifest hash |

Public keeps: Protocol, DTO, Manifest, Estimate DTO, Guards, Fake Resolver.  
Private implements formal resolve/assembly.

## 3. `WholeBookDataTransferManifest`

Fields (minimum): schema, version, book_id, book_snapshot_id, module_key, provider_key, model_id, execution_location, context_bundle_hash, selected_context_unit_ids, selected_chapter_ids, selected_paragraph_ids, source_character_count, estimated_input_tokens, estimated_output_tokens, estimated_cost, sends_source_text, sends_derived_text, retention_policy, consent_required, consent_fingerprint, generated_at.

**Must not** contain: novel body, API key, prompt text, provider raw response, payment info.

Rules:

1. User confirms **this** Manifest  
2. Manifest change → prior consent invalid  
3. Context / Model / Prompt Pack / Snapshot change → re-estimate + re-consent  
4. Manifest hash enters Run configuration fingerprint  

## 4. `WholeBookProviderEstimateService`

Replace placeholder `512/256`.

**Inputs:** Provider Input Bundle, provider_key, model_id, module, prompt_pack version, quality_profile, context_policy, retry_policy, pricing_version.

**Outputs:** estimated_input_tokens, estimated_output_tokens, estimated_total_tokens, estimated_cost_low/expected/high, max_retry_cost, pricing_version, estimate_method, confidence, warnings.

Rules:

1. Input tokens from **actual** pending messages (+ prompt tokens counted, text not returned)  
2. Output tokens from module policy (versioned)  
3. Retry cost shown separately  
4. Use existing pricing (`config/cloud_pricing.default.json` / runtime pricing path)  
5. **Unknown price ≠ ¥0**; block auto-confirm or hard warning  
6. Actual usage recorded post-call; estimate vs actual separated  
7. Single-run / daily budget checked before call and before each retry  
8. Cancel stops retries  
9. Internal cost ≠ commercial SKU  

First route remains: `aliyun_qwen_plus` / `qwen3.7-plus` / `balanced`  
(`PRIVATE_LAB_FIRST_*` + private `FIRST_ROUTE`).

## 5. Bailian adapter fix list (Agent U)

| # | Fix |
|---|-----|
| 1 | Accept resolved Provider Input Bundle |
| 2 | Separate system instruction vs source_data |
| 3 | Pass module output schema into structured response |
| 4 | Credential only via `ExistingCredentialServiceAdapter` at execute boundary |
| 5 | Never log messages / credentials |
| 6 | Timeout from `aliyun_timeout_seconds` |
| 7 | Cancellation via `cancellation_ref` |
| 8 | Bounded retries; budget re-check |
| 9 | Return actual token usage |
| 10 | Cost from pricing_version |
| 11 | Invalid JSON → private repair chain (not public invent) |
| 12 | Never forge success |
| 13 | Raw response not in Artifact / not returned to FE |

Live still gated by: Lab enabled + `WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE` + consent + budget + credential.

## 6. Ownership split

- **U:** Protocol, Manifest, Estimate, Bailian payload/estimate/cost, private message assembly / repair  
- **V:** Must consume Manifest/Estimate fingerprints on create; must not re-implement message assembly  
- **I:** Wire estimate/preflight routes into composition; Live Smoke harness
