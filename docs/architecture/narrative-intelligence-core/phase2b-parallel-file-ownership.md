# Phase 2B Parallel File Ownership

Baseline: `VERSION=1.0.5` @ `4cec5dbdf2f12669b389c845abf6de2e6a1ec28b` (`integration/narrative-phase2a`).

Machine-readable: [phase2b-parallel-file-ownership.json](./phase2b-parallel-file-ownership.json).

Public contract: `apps/api/app/narrative_core/private_engine_contract/`  
FE types: `apps/desktop/src/features/wholeBook/privateEngineContracts/`

## Phase 2B-P (CHG-036)

Branch: `feature/narrative-phase2b-core-engine-contract`  
Worktree: `D:\Dstorylens-wt-narrative-phase2b-contract`

Owns contract freeze only: Manifest/Loader/Provider Gateway/Prompt Pack/Context/Evidence/Module Spec/first-four modules/Validation/Evaluation/ownership docs/Change pre-registration. Protocols, DTOs, Fakes, validators, docs, contract tests — no real algorithms or formal prompts.

## Agent P — Private Engine Runtime (CHG-037)

Branch: `feature/narrative-phase2b-engine-runtime`  
Worktree: `D:\Dstorylens-wt-narrative-engine-runtime`

Manifest Loader, signature verify interface, Provider Gateway, Engine Runtime Adapter, Fake Private Engine. No formal algorithm or prompt.

## Agent Q — Context & Evidence (CHG-038)

Branch: `feature/narrative-phase2b-context-evidence`  
Worktree: `D:\Dstorylens-wt-narrative-context-evidence`

Snapshot Context, Context Unit/Bundle, Evidence Candidate/Validator, Native/Enhanced context. No model calls.

## Agent R — First Modules & Evaluation (CHG-039)

Branch: `feature/narrative-phase2b-core-modules`  
Worktree: `D:\Dstorylens-wt-narrative-core-modules`

Four Module Runner skeletons, Output Validator, Candidate Builder, Fake Prompt Pack, Evaluation Harness. No formal prompts; no real model calls.

## Integration (CHG-040)

Branch: `integration/narrative-phase2b`  
Worktree: `D:\Dstorylens-wt-narrative-phase2b-integration`

Merge P/Q/R; runtime composition; Fake Provider E2E; Module Spec consistency; Context→Evidence→Module→Candidate; Change Registry; README; integration tests.

Subsequent branches derive from Phase 2B-P final HEAD.

## Shared risk files

| Path | Risk | Owner |
|------|------|-------|
| `apps/api/app/main.py` | Must not enable production whole-book runs | Integration |
| `apps/api/app/db/models.py` | No new tables/migrations | Read-only |
| `apps/api/app/narrative_core/enums.py` | Module/stage key consistency | Shared read; Integration review |
| `apps/api/app/narrative_core/product_contract/` | Planning/Producer/Result maps via adapters only | R + Integration |
| `apps/api/app/narrative_core/run_shell_contract/` | Do not break Phase 2A Mock Lab | Read-only |
| `apps/api/app/narrative_core/services/whole_book_engine_registry.py` | Production default engine stays None | P + Integration |
| `apps/desktop/src/features/wholeBook/contracts/` | FE must not gain engine internals | Read-only; FE types only under `privateEngineContracts/` |
| `VERSION` / production gates | Untouched | Forbidden |

## Forbidden for all Phase 2B agents

Formal prompts/algorithms; real model calls; open production runs; flip ship/run/lab gates; migrations/new tables/FTS5/vector/Neo4j; VERSION/tag/baseline; push/build/publish; stash restore; private algorithm in public contract dirs.
