# Phase 2B-R Implementation Plan

**Change:** CHG-20260723-041  
**Branch:** `feature/narrative-phase2br-implementation-plan`  
**Worktree:** `D:\Dstorylens-wt-narrative-phase2br-plan`  
**Source:** `integration/narrative-phase2b` @ `737617f2576a49c94d539e665484a4cdba55a6a5`  
**VERSION:** 1.0.5 (unchanged)

本阶段只做审计与实现计划，不写正式 Prompt、不调模型、不开发真实算法、不开放正式整书 Run。

## 1. Current capability verdict (code-backed)

| Area | Current state | Key symbols / paths |
|------|---------------|---------------------|
| Runtime composition | Fake-only composition root | `PrivateWholeBookAnalysisRuntime`, `create_private_whole_book_analysis_runtime` in `apps/api/app/narrative_core/services/private_whole_book_analysis_runtime.py` (`production=True` raises) |
| Manifest / Loader / Adapter | Implemented for signed-manifest discovery | `private_engine_manifest_loader.py`, `private_engine_signature.py`, `private_engine_runtime_adapter.py` |
| Fake Engine / Provider | Synthetic only; `_NETWORK_FORBIDDEN=True` | `FakePrivateWholeBookEngine`, `FakeProviderAdapter`, `DefaultWholeBookProviderGateway` |
| Credential | Skeleton adapter; Fake path disabled | `ExistingCredentialServiceAdapter.enabled=False`; real store: `KeyringCredentialStore` / `CredentialStore` |
| Real Provider HTTP | Exists for chapter pipeline, **not** wired to whole-book gateway | `apps/api/app/model_gateway/registry.py` → `OpenAICompatibleProvider` for `aliyun_qwen_plus/max/flash`, `local_llama` |
| Budget | Mock/lab + chapter cloud budget; whole-book BudgetGuard is adapter-only | `BudgetGuard` Protocol; `BudgetGuardAdapter`; `apps/api/app/services/cloud_budget.py` |
| Context / Evidence | Pipeline + validators exist; Fake runners use them | `whole_book_context_pipeline.py`, `whole_book_evidence_pipeline.py`, `whole_book_evidence_validator.py` |
| Four modules | Spec + Fake runners only | `BOOK_OVERVIEW_SPEC`…`STORYLINES_SPEC`; `FakeBookOverviewRunner` etc. |
| Candidate persistence | Commands + recording sink only | `CandidatePersistenceAdapter`, `RecordingCandidatePersistenceSink` (`orm_written=False`) |
| Phase 1B services | Real ORM services available | `NarrativeEntityServiceImpl`, `NarrativeAssetService`, `NarrativeRelationServiceImpl`, `EvidenceReadService`, `ConflictService` / `ConflictCenterService` |
| Labs / gates | Mock Lab closed; formal Run disabled | `WHOLE_BOOK_MOCK_LAB_ENABLED=False`; `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=True`; `PRODUCTION_DEFAULT_ENGINE_ID=None`; `PRO_CAPABILITIES_SHIPPED=false` |

## 2. Topology choice

| Phase | Topology | Rationale |
|-------|----------|-----------|
| **2B-R development** | **A. Private Python Package** + independent private Git repo + Private Engine Lab | Fast iterate; same Protocol as public app; no packaging yet; local-first |
| **2F release prep** | **B. Signed private Sidecar** (primary) or **C. remote private service** for high-value strategies; **D. Hybrid** allowed later | Keep algorithms/prompts out of public install source; signed sidecar matches Windows packaging (`scripts/build_sidecar.ps1` is public API sidecar today — private engine sidecar is separate future artifact) |

Public App calls private Engine **only** via `storylens.private_engine.v1` Protocol / Manifest / Runtime Adapter / Provider Gateway. Modules must not HTTP.

## 3. First real Provider (no live calls this phase)

**Selected first path:** Aliyun Bailian OpenAI-compatible via existing gateway stack.

| Field | Value (from code/config) |
|-------|--------------------------|
| Provider key | `aliyun_qwen_plus` |
| Family | `aliyun_qwen` |
| Default model | `qwen3.7-plus` (`Settings.aliyun_plus_model`) |
| Endpoint resolver | `resolve_aliyun_compatible_base_url` → workspace MaaS or `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Context limit (gateway bootstrap) | `max_context_tokens=32768` |
| Structured output | `aliyun_structured_output_mode="json_object"`; `supports_json_object=True` |
| Timeout | `aliyun_timeout_seconds=300` |
| Retry | `aliyun_max_retries=3`; transport attempts/delays in `Settings` |
| Credential | OS keyring via `CredentialStore.get("aliyun_qwen_plus")` — **never** in private module DTO |
| Pricing source | `config/cloud_pricing.default.json` (`qwen3.7-plus` input 2.0 / output 8.0 per million) |
| Daily budget | `cloud_daily_request_limit=50`, `cloud_daily_token_limit=200000`, `cloud_daily_estimated_cost_limit=1.0` (`schemas/settings.py`) |

### Quality profile → route plan (not hard-coded in modules)

| QualityProfile | Planned Model Route | Current code support |
|----------------|---------------------|----------------------|
| `fast` | `aliyun_qwen_flash` / `qwen3.6-flash` | Registered; `manual_only=True` — enable only after Product/capability policy |
| `balanced` | `aliyun_qwen_plus` / `qwen3.7-plus` | **First real path** — connection test, scene canary, budget already exist |
| `high_quality` | `aliyun_qwen_max` / `qwen3.7-max` | Registered; `manual_only=True` — second wave |

Local OpenAI-compatible / llama-server remains secondary (manual profiles; not the first 2B-R path).

## 4. Private Lab (dev verification only)

| Gate | Value |
|------|-------|
| Env | `WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED` default **false**; only `development` / `test` |
| Header | `X-StoryLens-Private-Engine-Lab: 1` |
| Path | `POST/GET … /api/v1/labs/private-whole-book-runs` (planned) |
| Formal path | `POST /api/v1/books/{book_id}/whole-book-runs` stays disabled |
| Distinct from | Mock Lab (`WHOLE_BOOK_MOCK_LAB_ENABLED`, `X-StoryLens-Mock-Lab`) |

Must enforce: loopback, capability, credential present, data-transfer consent, estimate + daily budget, single-run budget, concurrency limit, cancel, resume fingerprint, OpenAPI production isolation.

## 5. Four modules — shared pipeline

```
Snapshot → Context Bundle → Provider Request → Structured Output
→ Schema Validation → Reference Validation → Evidence Candidate
→ Evidence Validation → Coverage → Conflict Detection
→ Candidate Persistence → Result Projection
```

| Module | Must support (contract already flags) | Private work |
|--------|----------------------------------------|--------------|
| `book_overview` | multi/unknown protagonist, partial, multi-storyline, Evidence | Real runner + Prompt Pack |
| `structure_stages` | variable stages, non-contiguous ranges, turning-point Evidence, no forced 3-act | Real runner + Prompt Pack |
| `chapter_functions` | multi-label, primary/secondary, side/flashback/empty, Evidence | Real runner + Prompt Pack |
| `storylines` | main/side/relation/quest, multi-membership, pause/resume/terminate, Evidence | Real runner + Prompt Pack |

Forbidden: per-novel/author/character branches; fixed three-act; single-sample thresholds.

## 6. Candidate persistence plan

Replace Integration recording-only path with Phase 1B service adapter:

- `Command → Service Adapter` over `NarrativeEntityServiceImpl`, `NarrativeAssetService`, `NarrativeRelationServiceImpl`, evidence writers, `ConflictService`, stage artifact writers already used by `NarrativeAssetWriterAdapter` / `NarrativeRelationWriterAdapter`
- Transaction per validated module batch; candidate-only; no auto canonical/confirm/lock; no overwrite of user versions
- Bind `run_id`, `run_stage_id`, `book_snapshot_id`, engine/module/prompt_pack versions, configuration + output fingerprints
- Evidence after Asset/Relation ids exist; duplicate-safe / retry-idempotent; failed validation & budget-denied → no write
- **No new Migration** unless Integration proves schema cannot carry metadata (then block and escalate — do not invent tables in 2B-R Agents)

## 7. Context & cost strategy (generic bands)

Thresholds must be versioned, configurable, fingerprint-included; **not** locked until multi-work eval.

| Band | Strategy (generic) |
|------|--------------------|
| Small | Catalog + full chapter batches; fewer splits |
| Medium | Chapter batches + paragraph grouping (`ParagraphGroupingPolicy` initial max=40/overlap=2) |
| Large | Chapter batches + Evidence secondary locate; stage results reused |
| Very long | Strict provider-context shrink; no unconditional full-book upload; cross-chapter aggregate only when needed |

Always: book catalog/metadata first; never dump full raw novel into logs/artifacts/API.

## 8. Output repair boundary

| Allowed (private Engine) | Forbidden (esp. public App) |
|--------------------------|-----------------------------|
| JSON extract, schema repair, type/enum normalize, retry | Invent plot conclusions without Evidence |
| Reject missing fields / invalid refs | Hardcoded plot rules; forge schema-ok results |
| | Persist/return raw model text as Asset/UI payload |

## 9. Parallel execution

| Role | Change | Branch / Worktree |
|------|--------|-------------------|
| Agent S | CHG-042 | `feature/narrative-phase2br-private-runtime` / `D:\Dstorylens-wt-narrative-private-runtime` + private repo branch |
| Agent T | CHG-043 | `feature/narrative-phase2br-real-modules` / `D:\Dstorylens-wt-narrative-real-modules` + separate private worktree/branch |
| Integration | CHG-044 | `integration/narrative-phase2br` / `D:\Dstorylens-wt-narrative-phase2br-integration` |

File ownership: `phase2br-parallel-file-ownership.md` / `.json`.

## 10. Cross-repo versioning

Each Change records: public commit, private commit, engine id/version, prompt pack id/version, provider route, modules, tests, compatibility, build artifact (if any), manifest hash. Private **source** never enters public git; private commit hash may appear in Change Registry only.

Fingerprint reproducibility: `Public commit + Private commit + Engine manifest + Prompt pack manifest`.

## 11. Acceptance

- Auto tests → status max **tested**
- **verified** only after manual Live Smoke (user-selected book, estimate/consent, four modules, Evidence jump, no auto-canonical, cancel/budget, no body/credential in logs)
- This planning phase does **not** run Live Smoke

## 12. Explicit non-goals (this Change)

No formal Prompt bodies; no model calls; no real algorithms; no private sidecar packaging; no gate flips; no Migration; no VERSION/tag/baseline/release edits; no push/build/publish.
