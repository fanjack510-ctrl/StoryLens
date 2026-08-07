# REAL_PATH_AUDIT — CHG-20260807-054

BLOCKER：RB-V120-L3-FREE-REAL-PATH-001
DATE：2026-08-07

## Call chain (intended)

```
Desktop / API POST .../whole-book/free/create
→ create_free_whole_book_analysis_v1
→ capability + consent + snapshot validate
→ create_whole_book_run_v1(ResultOrigin.formal)
→ generate_whole_book_windows_v1
→ start_whole_book_run_v1
→ execute_minimal_pipeline (shared)
   → extract_entities_events (GatewayWindowAnalysisTransport)
   → materialize_assets (DB only)
   → synthesize_overview (GatewayOverviewTransport)
   → synthesize_structure_stages (GatewayStructureTransport)
   → synthesize_chapter_functions (GatewayChapterFunctionsTransport)
→ WholeBookProviderOrchestrator.execute_provider_unit
→ transport.invoke → ModelGateway.generate(aliyun_qwen_plus / qwen3.7-plus)
→ asset materialization / project_result / finalize
```

## Answers

### 1. Why Fixture works

`create_fixture_free_whole_book_analysis_v1` fully orchestrates snapshot → estimate → consent → run(`fixture`) → windows → `execute_fixture_minimal_pipeline_v1` with four `Fixture*Transport` classes that return deterministic contract payloads (no network).

### 2. Why Real is hard-disabled

`create_free_whole_book_analysis_v1` after consent validation:

1. If `!real_provider_enabled()` → `WHOLE_BOOK_REAL_PROVIDER_DISABLED`
2. **Else always** → `WHOLE_BOOK_CAPABILITY_DISABLED` (“真实 Provider 路径尚未在本版本开放”)

Also: Desktop defaults real flag off; no Free Real transports existed.

> **Post-fix (this CHG):** hard stub removed; formal create uses Gateway transports; Fixture Preview remains isolated (even when real flag ON).

### 3. Real Provider Adapter for Free modules?

**No.** Only `Fixture*` + test `CountingFakeWholeBookProvider`.
`AliyunNativeOverviewTransport` is a different protocol (Private/Native Overview), not `WholeBookProviderTransport`.

### 4. Can Whole-Book Units call generic Provider?

**Capability yes, wiring no.** Orchestrator only calls `transport.invoke`; ModelGateway/`aliyun_qwen_plus` exist but were never bridged for Free units. Attempts hard-coded `provider_id="fake"`.

### 5. Missing pieces

| Piece | Status |
|---|---|
| Capability gate hard stub | **Present (blocker)** |
| Real Free transports | **Missing** |
| Shared pipeline entry for formal | **Missing** (fixture-only executor) |
| Orchestrator result_payload return | **Missing** (caused double invoke for non-fixture) |
| Formal provenance validation | **Bug**: forbids ALL formal provenance |
| Scheduler | Sync for short sync L3-A; long books later |
| Desktop consent_id | Separate UX gap; API path is authoritative for this CHG |

## Implementation principle

Same Pipeline → Fixture Adapter (tests) OR Gateway/Aliyun Adapter (formal).
No second drifting Real business pipeline.
