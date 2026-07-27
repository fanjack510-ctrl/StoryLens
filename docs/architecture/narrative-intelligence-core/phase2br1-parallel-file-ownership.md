# Phase 2B-R1 Parallel File Ownership

Baseline public: `a8349c44b2b7ecebccb46b512ab77f1d8a0524c4`  
Baseline private: `61cdc3ad184c00e0ab19bcc87b61149293fc3598`  
Machine-readable: [phase2br1-parallel-file-ownership.json](./phase2br1-parallel-file-ownership.json)

Legend: **exists** | **planned**

## Agent U — Provider Context & Cost (CHG-046)

**Public:** `feature/narrative-phase2br1-provider-context-cost` → `D:\Dstorylens-wt-narrative-provider-context-cost`  
**Private:** `feature/phase2br1-provider-context-cost` → `D:\Dstorylens-private-engine-wt-provider-context-cost`

### Public (U)

| Path | Status |
|------|--------|
| `apps/api/app/narrative_core/private_engine_contract/provider_input.py` | planned |
| `apps/api/app/narrative_core/private_engine_contract/data_transfer.py` | planned |
| `apps/api/app/narrative_core/private_engine_contract/provider_estimate.py` | planned |
| `apps/api/app/narrative_core/services/whole_book_provider_gateway.py` | exists — Bailian live payload + estimate hooks |
| `apps/api/app/narrative_core/services/whole_book_provider_estimate_service.py` | planned |
| `apps/api/app/narrative_core/services/provider_input_bundle_resolver.py` | planned (Protocol + Fake) |
| `apps/api/app/narrative_core/services/data_transfer_consent_guard.py` | planned |
| `apps/api/app/narrative_core/run_shell_contract/private_engine_lab.py` | exists — estimate/consent constants only (coordinate) |
| `apps/api/tests/test_narrative_phase2br1_provider_context_cost.py` | planned |
| `release/changes/CHG-20260723-046.json` | planned |

### Private (U)

| Path | Status |
|------|--------|
| `src/storylens_private_engine/provider_input/resolver.py` | planned |
| `src/storylens_private_engine/provider_input/messages.py` | planned |
| `src/storylens_private_engine/prompt_pack/loader.py` | exists — assembly hooks |
| `src/storylens_private_engine/prompt_packs/` | exists — **read; do not rewrite formal Prompt bodies in R1 plan; U may add assembly glue only** |
| `src/storylens_private_engine/context/strategy.py` | exists — deepen for Provider windows |
| `src/storylens_private_engine/repair/structured_repair.py` | exists |
| `src/storylens_private_engine/provider_routing/policy.py` | exists |
| Private tests for resolver/estimate | planned |

**U forbidden:** Candidate Persistence, Lab Run Service, AnalysisRun wiring, module narrative algorithms rewrite.

## Agent V — Private Lab Runtime & Persistence (CHG-047)

**Public:** `feature/narrative-phase2br1-private-lab-runtime` → `D:\Dstorylens-wt-narrative-private-lab-runtime`  
**Private:** `feature/phase2br1-private-lab-runtime` → `D:\Dstorylens-private-engine-wt-private-lab-runtime`

### Public (V)

| Path | Status |
|------|--------|
| `apps/api/app/routers/whole_book_private_engine_lab_runs.py` | exists — expand beyond shell |
| `apps/api/app/narrative_core/services/private_engine_lab_run_service.py` | planned |
| `apps/api/app/narrative_core/services/private_engine_lab_authorization_service.py` | exists — create consent/estimate checks |
| `apps/api/app/narrative_core/services/candidate_persistence_adapter.py` | exists — Lab guarantees |
| `apps/api/app/narrative_core/services/private_whole_book_analysis_runtime.py` | exists — **read + thin Lab hooks; I owns composition final** |
| `apps/api/app/narrative_core/services/run_stage_service.py` | exists — use, careful |
| `apps/api/app/narrative_core/services/run_scope_service.py` | exists — use, careful |
| `apps/api/tests/test_narrative_phase2br1_private_lab_runtime.py` | planned |
| `release/changes/CHG-20260723-047.json` | planned |

### Private (V)

| Path | Status |
|------|--------|
| `src/storylens_private_engine/modules/*/runner.py` | exists — execution wiring / Evidence locators |
| `src/storylens_private_engine/modules/_shared/pipeline.py` | exists — consume resolved gateway; no HTTP |
| `src/storylens_private_engine/evidence/selection.py` | exists |
| `src/storylens_private_engine/validation/module_extra.py` | exists |
| Candidate command builders (private) | planned if needed |

**V forbidden:** Bailian `_execute_live` message assembly, EstimateService core, formal Prompt body authorship (coordinate with U).

## Integration (CHG-048)

**Public:** `integration/narrative-phase2br1` → `D:\Dstorylens-wt-narrative-phase2br1-integration`  
**Private:** `integration/phase2br1` → `D:\Dstorylens-private-engine-wt-phase2br1-integration`

| Path | Status | Risk |
|------|--------|------|
| `apps/api/app/narrative_core/services/private_whole_book_analysis_runtime.py` | exists | Composition root |
| `apps/api/app/main.py` | exists | Lab mount |
| `apps/api/app/model_gateway/registry.py` | exists | Announce if touched |
| `apps/api/app/core/config.py` | exists | Announce |
| `docs/architecture/README.md` | exists | Index |
| `docs/architecture/narrative-intelligence-core/README.md` | exists | Status rows |
| `apps/api/tests/test_narrative_phase2br1_integration.py` | planned | E2E dry |
| Live Smoke harness script (dev-only, default no live) | planned | |
| `release/changes/CHG-20260723-048.json` | planned | |

## Forbidden parallel edits

| Path | Rule |
|------|------|
| `VERSION` / `release/1.0.5` / tags / baseline | Forbidden |
| `apps/api/app/db/models.py` / migrations | Forbidden unless Schema Issue escalated |
| `productEdition.ts` PRO ship flag | Forbidden |
| Flip `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED` | Forbidden |
| Same private worktree for U and V | Forbidden |
| Formal Prompt bodies wholesale rewrite | Forbidden in R1 plan; U/V coordinate later |

## Change Registry ownership

| Change | Owner |
|--------|-------|
| CHG-045 | Plan |
| CHG-046 | Agent U |
| CHG-047 | Agent V |
| CHG-048 | Integration |
