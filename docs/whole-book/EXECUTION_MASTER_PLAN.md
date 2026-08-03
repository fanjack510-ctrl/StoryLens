# StoryLens Whole-Book Execution Master Plan

**Status:** frozen by WB-0.1 / CHG-20260728-002；**AMENDED BY CHG-20260803-044**（V1.2.0 Free scope reconciliation）  
**Target product version:** StoryLens **1.2.0**（Free 全书四模块）  
**Formal baseline:** StoryLens **v1.1.1**（integration train also carries 1.1.2→1.2.0 work）  
**Machine registry:** [`EXECUTION_REGISTRY.json`](./EXECUTION_REGISTRY.json)

## 0. V1.2.0 Free scope (CHG-20260803-044)

| Field | Value |
|---|---|
| FEATURE DEVELOPMENT COMPLETE | **YES** |
| FEATURE END STEP | **WB-2.2-CHAPTER-FUNCTIONS** |
| FREE MODULES | overview / characters_events / structure / chapter_functions（**4**） |
| PRO MODULES IN 1.2.0 | **0** |
| WB-2.3 Storylines | **deferred** → Pro / future（**not** next Free step） |
| WB-2.4 Phase2B first-four | **superseded** by current Free four |
| WB-3.x～WB-5.x | **out_of_scope_for_1.2.0** |
| WB-6.1～WB-6.3 | **out_of_scope_for_1.2.0_free_release** |
| Remaining Free release path | WB-2.2.1 → WB-2.2.2 → WB-2.2.3 → WB-6.4 → WB-6.5 |

Authoritative details: registry keys `v120_free_product_scope` / `v120_free_release_path` and evidence `release/evidence/whole-book/CHG-20260803-044/`.

Active Integration branch: `integration/1.2.0-after-1.1.2`（historical planned name `integration/whole-book-v120` retained for audit only）.

## 1. Purpose

This document freezes the execution system for native whole-book analysis after v1.1.1:

- baselines and branch strategy
- 37 historical Step IDs, Change IDs, Manual Gate IDs（audit spine；not the active Free 1.2.0 coding queue）
- V1.2.0 Free release substeps WB-2.2.1 / 2.2.2 / 2.2.3 + reused WB-6.4 / WB-6.5
- evidence paths, status flow, Sample S/M/L, Provider rules
- protected WIP worktrees
- parallel Agent / Integration rules
- re-acceptance rules when frozen contracts break

It does **not** by itself implement whole-book product features.

## 2. Frozen baselines (full SHA)

| Item | Value |
|---|---|
| Public worktree | `D:\Dstorylens-wt-narrative-phase2br1-integration` |
| Public branch at freeze | `release/1.1.1` |
| Public HEAD | `b2c6a89fa5b1be664120adfcaa7bb9dab514e3a3` |
| v1.1.1 Tag annotated | `6f7d88c41f8006176fe77dd92bdb06cf1c6683e3` |
| v1.1.1 Tag target (build source) | `38c85ab4eda0eaa03bd6a7bf8fda7d8deb11a5db` |
| Public base relation | CURRENT HEAD **contains** Tag target |
| VERSION | `1.1.1` |
| Private worktree | `D:\Dstorylens-private-engine-wt-phase2br1-integration` |
| Private branch | `integration/phase2br1` |
| Private HEAD | `30d8dad8cd649e832999874f7bf16cc1661cf221` |

Audit reference tip `b2c6a89…` matches current Public HEAD. Tag target matches audit.

## 3. Branch strategy (frozen; not created in WB-0.1)

| Rule | Value |
|---|---|
| Do not develop on | `release/1.1.1` |
| Public integration branch | `integration/whole-book-v120` |
| Private integration branch | `integration/whole-book-v120` |
| Suggested Public worktree | `D:\Dstorylens-wt-whole-book-v120-integration` |
| Suggested Private worktree | `D:\Dstorylens-private-engine-wt-whole-book-v120-integration` |
| Create Public branch from | `b2c6a89fa5b1be664120adfcaa7bb9dab514e3a3` |
| Create Private branch from | `30d8dad8cd649e832999874f7bf16cc1661cf221` |
| When to create | After **MG-WB-0.1 PASS**, before WB-0.2 implementation, **only with explicit user approval** |
| Created in WB-0.1 | **NO** |
| v1.1.1 Tag | immutable |
| Historical Releases | immutable |

## 4. Numbering

- **NUMBERED STEPS: 37** (`WB-0.1` … `WB-6.5`)
- **CHANGE IDS: 37** (`CHG-20260728-002` … `CHG-20260728-038`)
- **MANUAL GATES: 37** (`MG-WB-0.1` … `MG-WB-6.5`)
- **STEPS WITHOUT MANUAL GATE: 0**
- Audit change (read-only): `CHG-20260728-001` (not one of the 37 implementation steps)

Insertions must use sub-steps (`WB-1.3A` / `WB-1.3.1`) with a **new** Change and Manual Gate. Do not renumber frozen IDs.

Full table: see `EXECUTION_REGISTRY.json` → `steps`.

## 5. Status flows

### Whole-Book Step status

`planned → implementing → tested → manual verification → verified → integrated`

Rules:

1. Cursor may set implementing / tested / manual verification  
2. After automation, max status is **tested**  
3. Only user explicit PASS may set **verified**  
4. Failed Manual Gate blocks dependent steps  
5. **integrated** only after Integration + human PASS  
6. Cursor must not self-verify  
7. Ambiguous user reply → remain `manual verification`  
8. BLOCKED must not be skipped  

### Change Registry status (project tool)

`registered → implemented → tested → verified → ready-for-staging → ready → released`

WB `manual verification` maps to Change Registry **tested** + Manual Gate ready. WB `verified` requires user PASS then `change_registry.py mark … verified`.

## 6. Acceptance levels

See [`MANUAL_GATE_POLICY.md`](./MANUAL_GATE_POLICY.md). Defaults: **REAL PROVIDER CALLS = 0** unless user approves an L3 step.

## 7. Sample / Assumptions / Evidence / Agents

- Samples: [`SAMPLE_VALIDATION_POLICY.md`](./SAMPLE_VALIDATION_POLICY.md)  
- Protected WIP: [`PROTECTED_WORKTREES.md`](./PROTECTED_WORKTREES.md)  
- Assumptions A–H earliest gates: registry `high_risk_assumptions`  
- Evidence root: `release/evidence/whole-book/<STEP-ID>/`  
- Parallel Agents: max 3; Integration then Manual Gate; no Gate skip  

## 8. Contract break rule

If a frozen contract must change after a Gate PASS:

1. New Change  
2. Document impact  
3. Re-run affected Manual Gate(s)  
4. No silent semantic drift  

## 9. Registry verification

```powershell
python scripts/verify_whole_book_execution_registry.py
```

## 10. Historical next after MG-WB-0.1 PASS

1. Mark `CHG-20260728-002` verified (user-authorized)  
2. Freeze WB-0.1  
3. Propose WB-0.2 Prompt  
4. Optionally create `integration/whole-book-v120` worktrees (user-approved)  

**WB-0.2 must not start automatically.**

## 11. Next after MG-V1.2.0-SCOPE-RECONCILIATION PASS（current）

1. Mark `CHG-20260803-044` verified  
2. Authorize **WB-2.2.1-V120-E2E-STABILIZATION** only  
3. Do **not** start WB-2.3 / WB-2.4 / WB-3.x～WB-5.x / Pro UI for Free 1.2.0
