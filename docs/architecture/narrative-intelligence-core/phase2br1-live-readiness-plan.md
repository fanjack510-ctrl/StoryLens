# Phase 2B-R1 Live Readiness Plan

**Change:** CHG-20260723-045  
**Public branch:** `feature/narrative-phase2br1-live-readiness-plan`  
**Public worktree:** `D:\Dstorylens-wt-narrative-phase2br1-plan`  
**Public source:** `integration/narrative-phase2br` @ `a8349c44b2b7ecebccb46b512ab77f1d8a0524c4`  
**Private audit tip:** `D:\Dstorylens-private-engine-wt-integration` @ `61cdc3ad184c00e0ab19bcc87b61149293fc3598`  
**VERSION:** 1.0.5 (unchanged)

Plan-only. No model calls, no live Provider HTTP, no formal Prompt edits, no AnalysisRun creation.

## 1. Gap matrix (code-backed)

| # | Topic | Path / symbol | Current | Gap | Owner |
|---|-------|---------------|---------|-----|-------|
| 1 | HTTP Lab shell-only | `routers/whole_book_private_engine_lab_runs.py` `create_private_engine_lab_run` | In-memory `PrivateEngineLabSession`; dry health only | No runtime pipeline | **V** |
| 2 | `modules_implemented` | hardcoded `False` in create/get responses + session metadata | Always false | Must derive from real runner bind | **V** |
| 3 | AnalysisRun on create | Lab router only | Not created | Wire RunScope/RunStage services | **V** |
| 4 | AnalysisRunStage | none in Lab router | Missing | Stage per module | **V** |
| 5 | `PrivateWholeBookAnalysisRuntime` | Lab HTTP never calls it; Python factory exists | Composition ready offline | HTTP must call Lab factory | **V** + **I** |
| 6 | Four modules | private runners exist; HTTP unused | Python-only | Sequential Lab execution | **V** (private runners) |
| 7 | Candidate persistence | `Phase1BCandidatePersistenceSink.persist_commands` | Wired in Lab factory when session+book_id | HTTP path never reaches sink | **V** |
| 8 | Evidence persistence | via Phase1B sink → `attach_asset_evidence` / relation evidence | Exists | Same as #7 | **V** |
| 9 | Live messages | `BailianOpenAICompatibleProviderAdapter._execute_live` | `instruction_ref=…` / `input_bundle_ref=…` strings only | Must send resolved messages | **U** |
| 10 | `instruction_ref` resolve | private prompt pack refs; Bailian does not resolve | Ref echoed into message | Private resolver → system text | **U** (private) |
| 11 | `input_bundle_ref` resolve | context_bundle_ref only | Ref echoed | SnapshotTextRef → windows | **U** (private) |
| 12 | Body resolver | `SnapshotTextResolver` in context units; **no** ProviderInputBundleResolver | Text for context; not for Provider messages | New Protocol + private impl | **U** |
| 13 | Token estimate | `estimate`: `token_budget or 512` / output 256 | Placeholder | Estimate from real messages | **U** |
| 14 | Cost estimate | Adapter dry cost `0.0`; live `cost=None` | Pricing unused in adapter | Use `cloud_pricing` + unknown≠0 | **U** |
| 15 | Live usage record | tokens from `ModelResponse`; cost None | Incomplete | Record actual + pricing version | **U** |
| 16 | Cancel→Provider | Adapter `cancel` set; Lab cancel flips session only | No in-flight cancel to HTTP | Propagate cancellation_ref | **U**+**V** |
| 17 | Raw response logs | `assert_no_credential_in_logs`; messages not logged today | Risk if future debug | Forbid message/raw logging | **U**+**I** |
| 18 | Prompt Pack load | private `prompt_pack/loader.py`, `prompt_packs/` | Loads private packs | Keep private; public Manifest only | **U** (private assembly) |
| 19 | Phase1B adapter | `Phase1BCandidatePersistenceSink` | Implemented | Extend transaction/idempotency for Lab Run | **V** |
| 20 | Result API vs Lab Run | `whole_book_results.py` needs AnalysisRun id | Lab sessions not AnalysisRun | Lab create → real run_id | **V**+**I** |

## 2. Topology for R1 implementation

```
Preflight → DataTransferManifest → Estimate → User Confirm
→ Create Private Lab Run (AnalysisRun + Stages)
→ PrivateWholeBookAnalysisRuntime (lab_mode)
→ Sequential modules: overview → structure → chapter_functions → storylines
→ Phase1BCandidatePersistenceSink → Result Projection
```

Formal `POST /api/v1/books/{book_id}/whole-book-runs` stays **disabled**.

## 3. Provider context assembly (frozen direction)

```
SnapshotTextRef → Context Bundle → Module Context Plan
→ ProviderInputBundleResolver → Private Prompt Pack
→ Provider Messages → Provider Gateway
```

- Public: Protocol / DTO / Manifest / Estimate / Guards / Fake Resolver  
- Private: instruction resolve, unit selection, windows, messages, repair, evidence strategy  

Rules: body in-memory only; never long-lived Request DTO / audit / logs / artifacts / API; instruction ≠ source_data; untrusted novel text; context-limit; no default full-book upload.

## 4. Parallel agents

| Agent | Change | Role |
|-------|--------|------|
| **U** | CHG-046 | Provider Input Bundle, Manifest, Estimate, Bailian live payload fix, consent/budget guards |
| **V** | CHG-047 | Private Lab HTTP→Run/Stage/Runtime, sequential modules, Candidate/Evidence persistence |
| **Integration** | CHG-048 | Composition root, main mount, E2E, Live Smoke harness |

Ownership: `phase2br1-parallel-file-ownership.md` / `.json`.

## 5. Acceptance gates (after Integration)

- Auto tests → max **tested**  
- **verified** only after manual Live Smoke (Manifest confirm, real estimate, four modules sequential, Evidence jump, no auto-canonical, cancel/budget, log hygiene)  
- CHG-041～044 stay **tested** until that Smoke (do not auto-upgrade in R1 plan)

## 6. Non-goals (this Change)

No live HTTP; no Prompt body edits; no AnalysisRun writes; no Migration; no gate flips; no VERSION/tag/baseline; no push/build/publish.
