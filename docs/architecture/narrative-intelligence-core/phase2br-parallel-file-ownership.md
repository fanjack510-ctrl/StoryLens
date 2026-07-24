# Phase 2B-R Parallel File Ownership

Baseline: `VERSION=1.0.5` @ `737617f2576a49c94d539e665484a4cdba55a6a5` (`integration/narrative-phase2b`).

Machine-readable: [phase2br-parallel-file-ownership.json](./phase2br-parallel-file-ownership.json).

Legend: **exists** = present at baseline; **planned** = Agent may create; do not invent outside ownership.

## Agent S — Private Runtime and Provider (CHG-042)

**Public branch:** `feature/narrative-phase2br-private-runtime`  
**Public worktree:** `D:\Dstorylens-wt-narrative-private-runtime`  
**Private repo:** `D:\Dstorylens-private-engine` (create if absent; else audit-only)  
**Private branch suggestion:** `feature/narrative-phase2br-private-runtime`

### Public repo — Agent S owns

| Path | Status | Notes |
|------|--------|-------|
| `apps/api/app/narrative_core/services/whole_book_provider_gateway.py` | exists | Add real Bailian `ProviderAdapter`; keep Fake; credential boundary |
| `apps/api/app/narrative_core/services/private_engine_manifest_loader.py` | exists | Dev load paths for private package |
| `apps/api/app/narrative_core/services/private_engine_signature.py` | exists | Dev signature hooks; production unsigned reject stays |
| `apps/api/app/narrative_core/services/private_engine_runtime_adapter.py` | exists | Adapt private package entry |
| `apps/api/app/narrative_core/services/fake_private_whole_book_engine.py` | exists | Keep Fake; do not remove |
| `apps/api/app/narrative_core/services/fake_prompt_pack.py` | exists | Keep Fake; formal packs stay private |
| `apps/api/app/narrative_core/run_shell_contract/mock_lab.py` | exists | **Read-only** — do not overload Mock Lab |
| `apps/api/app/narrative_core/run_shell_contract/private_engine_lab.py` | planned | New Private Lab contract constants/auth eval |
| `apps/api/app/narrative_core/services/private_engine_lab_authorization_service.py` | planned | Mirror mock lab auth pattern |
| `apps/api/app/routers/whole_book_private_engine_lab_runs.py` | planned | Lab router only |
| `apps/api/app/main.py` | shared risk | Mount Lab only under env gates; Integration co-owns final wire |
| `apps/api/tests/test_narrative_phase2br_private_runtime.py` | planned | Unit/contract for adapter/lab/provider fake+dry |
| `docs/architecture/narrative-intelligence-core/phase2br-provider-and-budget-plan.md` | exists | May append implementation notes only if needed |
| `docs/architecture/narrative-intelligence-core/phase2br-live-analysis-safety.md` | exists | May append implementation notes |
| `release/changes/CHG-20260723-042.json` | planned/registered | S owns updates |

### Private repo — Agent S owns

| Path | Status | Notes |
|------|--------|-------|
| `README.md` | planned | Private repo purpose |
| `pyproject.toml` / package layout | planned | Importable private package |
| `src/storylens_private_engine/__init__.py` | planned | Package root |
| `src/storylens_private_engine/runtime/entry.py` | planned | Engine entry satisfying Protocol |
| `src/storylens_private_engine/prompt_pack/loader.py` | planned | Load packs; **no formal bodies required in first S commit if T owns packs** — coordinate: S owns loader + empty pack schema; T fills bodies |
| `src/storylens_private_engine/prompt_pack/manifest.py` | planned | Private-side manifest helpers |
| `src/storylens_private_engine/provider_routing/policy.py` | planned | Quality→route tables |
| `src/storylens_private_engine/repair/structured_repair.py` | planned | Repair algorithms (no public copy) |
| `tests/` private unit tests | planned | No live Provider by default |
| **Forbidden for S** | — | Four module narrative algorithms (`book_overview` etc. runners) |

## Agent T — First Four Real Modules (CHG-043)

**Public branch:** `feature/narrative-phase2br-real-modules`  
**Public worktree:** `D:\Dstorylens-wt-narrative-real-modules`  
**Private worktree/branch:** separate from S (e.g. `D:\Dstorylens-private-engine-wt-modules` or branch `feature/narrative-phase2br-real-modules`)

### Public repo — Agent T owns

| Path | Status | Notes |
|------|--------|-------|
| `apps/api/app/narrative_core/services/whole_book_module_runner.py` | exists | Keep Fake runners; add adapters calling private runners via Protocol |
| `apps/api/app/narrative_core/services/whole_book_module_output_validator.py` | exists | Extend public validation wiring only |
| `apps/api/app/narrative_core/services/whole_book_candidate_builder.py` | exists | Candidate command building |
| `apps/api/app/narrative_core/services/candidate_persistence_adapter.py` | exists | Add Phase 1B service sink (**not** recording-only); no Migration |
| `apps/api/app/narrative_core/services/whole_book_evaluation_harness.py` | exists | Eval case hooks for 2B-V prep |
| `apps/api/app/narrative_core/services/evidence_validator_runtime_adapter.py` | exists | Bridge only |
| `apps/api/app/narrative_core/services/whole_book_context_pipeline.py` | exists | **Read + thin hooks**; proprietary strategy stays private |
| `apps/api/app/narrative_core/services/whole_book_evidence_pipeline.py` | exists | Same |
| `apps/api/tests/test_narrative_phase2br_real_modules.py` | planned | Synthetic/authorized fixtures only |
| `release/changes/CHG-20260723-043.json` | planned/registered | T owns updates |

### Private repo — Agent T owns

| Path | Status | Notes |
|------|--------|-------|
| `src/storylens_private_engine/modules/book_overview/` | planned | Runner + prompts + tests |
| `src/storylens_private_engine/modules/structure_stages/` | planned | |
| `src/storylens_private_engine/modules/chapter_functions/` | planned | |
| `src/storylens_private_engine/modules/storylines/` | planned | |
| `src/storylens_private_engine/prompt_packs/book_overview/` | planned | Formal Prompt Pack bodies |
| `src/storylens_private_engine/prompt_packs/structure_stages/` | planned | |
| `src/storylens_private_engine/prompt_packs/chapter_functions/` | planned | |
| `src/storylens_private_engine/prompt_packs/storylines/` | planned | |
| `src/storylens_private_engine/prompt_packs/_shared/` | planned | Shared base instructions |
| `src/storylens_private_engine/context/strategy.py` | planned | Proprietary context policy |
| `src/storylens_private_engine/evidence/selection.py` | planned | Proprietary evidence selection |
| `src/storylens_private_engine/validation/module_extra.py` | planned | Module-specific validation supplements |
| **Forbidden for T** | — | Provider HTTP; CredentialStore; Manifest Loader core; Lab router |

### Prompt Pack packaging rule

- **One Prompt Pack per module** + shared base pack referenced by id/version  
- Public repo stores only `PromptPackManifest` metadata (id/version/hash/signature/schema/compat) under contract / engine manifests  
- Formal bodies **only** in private repo  

## Integration (CHG-044)

**Branch:** `integration/narrative-phase2br`  
**Worktree:** `D:\Dstorylens-wt-narrative-phase2br-integration`

Owns:

| Path | Status |
|------|--------|
| `apps/api/app/narrative_core/services/private_whole_book_analysis_runtime.py` | exists — composition root |
| `apps/api/app/narrative_core/services/whole_book_context_bundle_mapper.py` | exists |
| `apps/api/app/narrative_core/services/paragraph_grouping_policy.py` | exists |
| `apps/api/app/main.py` | final Lab mount |
| `apps/api/tests/test_narrative_phase2br_integration.py` | planned |
| Merge of public S/T + private S/T | — |
| `release/changes/CHG-20260723-044.json` | Integration |
| README indexes | with CHG-041 coordination |

## Forbidden parallel-edit files

| Path | Reason | Owner |
|------|--------|-------|
| `VERSION` | Freeze | Forbidden |
| `apps/api/app/db/models.py` | No schema drift | Forbidden / escalate |
| `apps/api/app/narrative_core/migrations/` | No new Migration | Forbidden |
| `apps/desktop/src/services/productEdition.ts` | `PRO_CAPABILITIES_SHIPPED` | Forbidden |
| `apps/api/app/narrative_core/contracts/api_dto.py` | `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED` | Forbidden to flip |
| `apps/api/app/narrative_core/services/whole_book_engine_registry.py` | `PRODUCTION_DEFAULT_ENGINE_ID` | Read-only unless Integration |
| `release/1.0.5/**`, tags, baseline | Release freeze | Forbidden |
| Same private working directory used by S and T | Collision | Forbidden |

## Shared ownership (serialize)

| Path | Rule |
|------|------|
| `apps/api/app/main.py` | S drafts Lab mount; Integration lands |
| `private_engine_contract/prompt_pack.py` | Metadata only; Integration reviews |
| `private_engine_contract/module_spec.py` | Read-only unless Integration-approved flag tweak |
| `Provider registry` `model_gateway/registry.py` | Prefer Adapter wrap; S may touch if required — announce |
| Change Registry `release/unreleased.json` | Integration / plan agent for pool; each agent updates own CHG file |
| `docs/architecture/README.md` + `narrative-intelligence-core/README.md` | CHG-041 seeds; Integration updates status rows |

## Change Registry ownership

| Change | Owner |
|--------|-------|
| CHG-041 | Plan agent (this branch) |
| CHG-042 | Agent S |
| CHG-043 | Agent T |
| CHG-044 | Integration |

## Status caps

- CHG-036: `verified` (keep)  
- CHG-037–040: `tested` (do not auto-upgrade)  
- CHG-041: max `tested`  
- CHG-042–044: start `registered`; Implementation may reach `tested`; `verified` only after Live Smoke (Integration + user)
