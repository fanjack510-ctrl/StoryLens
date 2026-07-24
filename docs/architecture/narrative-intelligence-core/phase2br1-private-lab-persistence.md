# Phase 2B-R1 Private Lab Persistence

**Change:** CHG-20260723-045 (plan) → implement CHG-047 (Agent V)

## 1. Current HTTP Lab (shell-only)

`apps/api/app/routers/whole_book_private_engine_lab_runs.py`

| Endpoint today | Behavior |
|----------------|----------|
| `POST ""` | In-memory session; `modules_implemented=False`; `create_lab_provider_gateway(dry_run=True)` health |
| `GET /_meta/contract` | Gate assertions |
| `GET /{lab_run_id}` | Session view |
| `POST /{lab_run_id}/cancel` | Flip session cancelled |

Does **not**: create `AnalysisRun` / `AnalysisRunStage`, call `PrivateWholeBookAnalysisRuntime`, run modules, persist candidates/evidence.

## 2. Target Lab API (extend same prefix)

Prefix remains: `/api/v1/labs/private-whole-book-runs`  
(`PRIVATE_ENGINE_LAB_API_PREFIX`)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/preflight` | No Run; Snapshot/capability/gate checks |
| POST | `/estimate` | Manifest + Estimate; no Run |
| POST | `` | Create Run after consent+estimate fingerprints |
| GET | `/{run_id}` | AnalysisRun-backed Lab view |
| GET | `/{run_id}/stages` | RunStages |
| POST | `/{run_id}/cancel` | Cancel + Provider cancel |
| POST | `/{run_id}/resume` | Fingerprint-compatible resume |
| POST | `/{run_id}/stages/{stage_key}/retry` | Bounded retry |

Keep: development/test, loopback, Header `X-StoryLens-Private-Engine-Lab: 1`, default env false, production OpenAPI unregistered, no formal FE nav.

Formal create `POST /api/v1/books/{book_id}/whole-book-runs` stays disabled.

## 3. Create requirements

1. Validate `consent_fingerprint` vs Manifest  
2. Validate estimate fingerprint  
3. Snapshot unchanged (id + content_hash)  
4. Budget OK (single + daily)  
5. Credential present for non-dry  
6. Provider health  
7. Capability OK  
8. Reject non-Lab runs on Lab endpoints  
9. One active Lab run per book (existing concurrency check)  

## 4. Execution order (Live Smoke v1)

1. `book_overview`  
2. `structure_stages`  
3. `chapter_functions`  
4. `storylines`  

**No parallel four-module first wave.**

Per module: module/prompt versions, context plan, estimate, provider usage, output fingerprint, evidence coverage, validation report, stage artifact, persistence result.

## 5. Reuse existing services

| Concern | Existing symbols |
|---------|------------------|
| Runtime | `create_lab_private_whole_book_analysis_runtime`, `PrivateWholeBookAnalysisRuntime.execute_module_pipeline` |
| Run/Stage | `RunScopeService`, `RunStageService`, Phase 2A lifecycle patterns |
| Results | `whole_book_results.py` / `WholeBookResultIndexService` |
| Persistence | `Phase1BCandidatePersistenceSink` |
| Asset write | `NarrativeAssetWriterAdapter`, `NarrativeAssetService` |
| Relation | `NarrativeRelationWriterAdapter`, `NarrativeRelationServiceImpl` |
| Evidence | `attach_asset_evidence`, relation evidence attach; `DefaultEvidenceValidator` |
| Conflict | `ConflictService` / conflict sink in engine adapters |
| Artifact | `ArtifactWriterAdapter` |
| Entity | `NarrativeEntityServiceImpl` (when needed) |

## 6. Persistence contract (Agent V)

Evolve / wrap `Phase1BCandidatePersistenceSink` as Lab-facing adapter with explicit methods:

`persist_entities`, `persist_assets`, `persist_relations`, `persist_evidence`, `persist_conflicts`, `persist_artifact` (or keep single `persist_commands` with stronger guarantees).

Must:

1. Per-module transaction  
2. Write only after full validation  
3. Candidate-only; no auto canonical/confirm/corrected/lock  
4. No overwrite user canonical  
5. Require run_id, run_stage_id, snapshot_id, engine/module/prompt versions, config+output fingerprints  
6. Evidence bound to correct Version  
7. Idempotent duplicate / retry  
8. Conflicts not auto-adjudicated  
9. Failed validation / budget deny / cancelled unfinished → no write  
10. Completed modules retained  

**No new Migration** unless Schema Issue escalated (evidence tables lack run_id today — provenance via parent version / attributes_json; document only).

## 7. Evidence chain

Locators: snapshot_chapter_id, snapshot_paragraph_id, stable_paragraph_id, paragraph_content_hash, start/end offsets, role, claim/output ref.

Private may select; public `DefaultEvidenceValidator` **must** final-validate. Hash/offset/cross-book/cross-snapshot reject. Derived summary not final Evidence. Key claims without Evidence not accepted. Result API reads Evidence; preview not large body dump; jump uses Snapshot.

## 8. Cancel / Resume / Retry

- Cancel must set AnalysisRun/Stage cancelled **and** Provider `cancellation_ref`  
- Resume only if fingerprints match (engine, prompt_pack, config, snapshot, Manifest)  
- Retry stage re-checks budget + consent validity  

## 9. Ownership

- **V:** Lab service, HTTP routes beyond shell, Run/Stage wiring, persistence, sequential module orchestration  
- **U:** Manifest/Estimate consumed by V; no persistence ownership  
- **I:** Composition + Live Smoke harness + Result API Lab compatibility
