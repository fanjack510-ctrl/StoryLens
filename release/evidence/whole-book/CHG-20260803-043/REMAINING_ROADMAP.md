# CHG-20260803-043 — V1.2.0 Remaining Roadmap (read-only)

## WB-2.2 closeout
- MG-WB-2.2 CHAPTER FUNCTIONS ACCEPTANCE：**PASSED**
- CHG-040 / 041 / 042 / WB-2.2 / CHG-043 → **verified**
- PRODUCT CODE MODIFIED：**NO**
- REAL PROVIDER CALLS：**0**
- FORMAL DATABASE WRITES：**0**

## Product baseline after WB-2.2
| Module | Status |
|---|---|
| 全书总览 | available |
| 主要人物与关键事件 | available |
| 故事结构 | available |
| 章节功能 | available |
| FREE MODULE COUNT | **4** |
| PRO PLANNED MODULE COUNT | **8** |
| PRO PURCHASE UI | **ABSENT** |
| DATABASE MIGRATION FOR WB-2.2 | **NO** |

## Source consistency
**CONFLICT** — do not auto-start WB-2.3 coding.

| Source | Location | Claim |
|---|---|---|
| EXECUTION_REGISTRY | `docs/whole-book/EXECUTION_REGISTRY.json` L4, L469–L493 | target=1.2.0; WB-2.2.next=`WB-2.3-STORYLINES`; WB-2.3 planned L3 |
| CHG-019 recovery | `release/changes/CHG-20260728-019.json` acceptance | Free chapter_functions available; **storylines remains Pro** |
| Free/Pro scope freeze | `release/changes/CHG-20260728-039.json` | Free four + Pro planned capabilities |
| Phase2B first-four | `docs/architecture/narrative-intelligence-core/phase2b-first-four-modules.md` A–D | overview / structure / chapter_functions / **storylines** |
| WB-2.4 title | registry order 20 | “First-four product integration” depends on WB-2.3 |
| Step roadmap | `docs/architecture/storylens-step-roadmap.md` L18–L19 | STEP 3=1.2.0 Pro Foundation; STEP 4=**1.3.0** 结构/故事线/章节功能 |
| Branch strategy | registry `branch_strategy` | `integration/whole-book-v120` |
| Actual Integration | current worktree | `integration/1.2.0-after-1.1.2` |
| CHG-020 / WB-2.3 evidence | — | **ABSENT** (`CHG-20260728-020.json` missing; no `WB-2.3-STORYLINES/` dir) |
| Registry lag | WB-0.6…WB-1.10 | still `planned` while WB-2.1/2.2 progressed |

### “First four” naming collision
- **Product Free four (current baseline):** overview, characters_events, structure, chapter_functions
- **Phase2B / registry first-four:** overview, structure_stages, chapter_functions, storylines

## Formal answers (section 七)
1. WB-2.3 EXISTS：**YES** — `WB-2.3-STORYLINES` / title Storylines / MG-WB-2.3 / L3 / CHG-20260728-020 (change file absent)
2. Formal name：**WB-2.3-STORYLINES — Storylines**
3. REQUIRED FOR V1.2.0：**UNRESOLVED** (registry chain YES; Free scope + CHG-019 say Pro / not Free four)
4. WB-2.x after WB-2.2：**YES in registry** — WB-2.3 then WB-2.4; **whether required for Free V1.2.0 release = UNRESOLVED**
5. End-to-end integration step：**WB-2.4-FIRST-FOUR-PRODUCT** exists (depends on WB-2.3) — may not match Free-four product meaning
6. Real Provider L3：**many L3 steps** (WB-2.3, WB-3.x, WB-4.x, WB-5.x…); no single dedicated “real provider acceptance only” step; L3 policy in registry `acceptance_levels.L3`
7. Long-book / performance：**no dedicated step_id** named long-book/performance; Sample S/M/L via `SAMPLE_VALIDATION_POLICY.md`; long-book UI pagination already in MG-WB-2.2
8. Installer / upgrade：**WB-6.4-120-RC** (L4 rc build/smoke), **WB-6.5-120-STABLE** (L4 Stable); no separate named “upgrade compatibility” step_id
9. RC / Release Gate：**YES** — WB-6.4 (RC) + WB-6.5 (Stable)
10. Formal steps remaining to Stable **if registry chain followed literally:** orders 19–37 = **19** planned steps — **but count is not authoritative for Free V1.2.0 until scope conflict resolved**

## Classification

### A. Must complete before release (evidence-supported candidates; scope-dependent)
| Item | Source | Status | Blocks release? | Depends | Gate |
|---|---|---|---|---|---|
| Scope/registry reconciliation (docs) | CHG-043 this file; registry vs CHG-019/039/roadmap | **required next** | YES (blocks choosing next code step) | WB-2.2 verified | User decision + docs Change |
| WB-2.3-STORYLINES | registry L482–L493 | planned | **UNRESOLVED** | WB-2.2 | MG-WB-2.3 L3 |
| WB-2.4-FIRST-FOUR-PRODUCT | registry L497–L508 | planned | **UNRESOLVED** (name collision) | WB-2.3 | MG-WB-2.4 |
| WB-6.4-120-RC | registry L737–L748 | planned | YES if following registry to Stable | WB-6.3 | MG-WB-6.4 L4 |
| WB-6.5-120-STABLE | registry L752–L761 | planned | YES for Stable tag | WB-6.4 | MG-WB-6.5 L4 |
| Real Provider L3 acceptance | L3 steps + MANUAL_GATE_POLICY | not started as dedicated wave | YES before claiming production algorithm quality | user approval | per-step MG |
| Pause/resume recovery | WB-1.8 (registry lag planned) | registry planned; product may already have pieces | likely YES for install-grade | WB-1.7 | MG-WB-1.8 |
| Cost/quota product | WB-6.3 | planned | likely YES for paid/quotas; Free cost consent already in modules | WB-6.2 | MG-WB-6.3 |

### B. Should handle before release
| Item | Source | Status | Blocks? |
|---|---|---|---|
| check_project.py TIMEOUT | CHG-042 TEST_RESULTS / BASELINE | TIMEOUT | **treat as release process blocker** until diagnosed |
| Registry/version-lock suite failures | pytest_full_summary.txt (change_registry_check, version_is_1_0_5, gates_and_version_locked, …) | failing | YES for clean release gate unless formal exceptions |
| Collection ImportErrors (6) | native_overview_* / http_replay_* | ERROR | YES to triage (env vs product) |
| Scene fake provider pipeline | test_scene_pipeline baseline fail | failing on public base | triage — may be debt or main-chain |
| Dev harness isolation in production builds | WB-2.2 harness DEV-gated (Integration) | implemented | confirm in RC build |
| Registry status lag WB-0.6–1.10 still planned | EXECUTION_REGISTRY | lag | consistency debt before RC |

### C. Formal debt allowed (candidates; not auto non-blocking)
| Item | Source | Notes |
|---|---|---|
| Vitest readerJourney legacy 30 failed | BASELINE_FAILURE_COMPARISON | same count pre/post WB-2.2; classify after owner review |
| Historical phase2b* version locks expecting 1.0.5 | pytest summary | outdated version pin class |
| Pro license private key test / Pro insights gate tests | pytest summary | Pro path; may be debt if Pro out of Free V1.2.0 |
| Pre-existing scene pipeline fail | BASELINE | preserved; not WB-2.2 new |

### D. Out of V1.2.0 Free scope (unless scope decision reverses)
| Item | Source |
|---|---|
| Pro eight modules productization | CHG-039; Free/Pro freeze |
| WB-6.1 Pro product UI / purchase / License | registry WB-6.1; MG-WB-2.2 ABSENT purchase UI |
| WB-3.x–WB-5.x Pro-depth modules (arcs, GCC, foreshadow, diagnosis, …) | registry phases WB-3…5 |
| STEP 4 content if roadmap 1.3.0 wins | storylens-step-roadmap.md L19 |
| New analysis modules beyond Free four | product baseline |

## Test debt audit (no fixes this round)
Honesty facts (do not rewrite):
- Public: **2114 passed / 48 failed / 6 errors / 54 skipped**; New WB-2.2 failures **0**
- Vitest: **1376 passed / 30 failed**; New **0**
- check_project: **TIMEOUT**

| Class | Items |
|---|---|
| WB-2.2 新增失败 | **0** (Public + Vitest) |
| V1.2.0 主链阻塞候选 | check_project TIMEOUT; version/gate/registry lock fails affecting release tooling; native_overview ImportError cluster (triage) |
| 版本锁 / Registry 债务 | phase* `change_registry_check`, `version_is_1_0_5`, `gates_and_version_locked`, `test_version_unchanged` |
| 环境依赖 | live_network_gate / live transport tests; check_project TIMEOUT |
| 过期测试 | 1.0.5 version pins; some phase2br1 acceptance closure |
| 可接受正式例外 | **none formally recorded this round** — do not auto-exempt |
| 必须修复但尚未修复 | **unresolved pending triage wave** — not claimed non-blocking |

## Compressed path to V1.2.0 Release (shortest reliable; conflict-aware)

### Wave 0 — NEXT (docs only)
- **ID:** `V1.2.0-SCOPE-REGISTRY-RECONCILIATION` (docs Change; **not** a new numbered WB product step until authorized)
- **Goal:** Resolve Free-four vs Phase2B-first-four vs registry WB-2.3/2.4 vs roadmap 1.3.0; freeze which steps are in/out for Free V1.2.0
- Product code：**NO** | Public docs：**YES** | Private：**NO** | Real Provider：**NO** | Manual：**YES** (user decision) | Installer：**NO**
- Preconditions: WB-2.2 verified
- Done when: SOURCE CONSISTENCY=PASS; explicit list of mandatory WB IDs for Free V1.2.0; WB-2.3 in/out decided

### Wave 1 — contingent on Wave 0
- If storylines **in** Free/registry path: implement **WB-2.3** then **WB-2.4** (product code YES; L3 manual; Provider per gate)
- If storylines **out** of Free V1.2.0: skip/defer WB-2.3; redefine or replace WB-2.4 as **Free-four E2E** (may need authorized sub-step — do not invent silently)

### Wave 2 — Stabilization / debt triage (mostly tests/docs; some code)
- check_project diagnosis; registry lag; release-blocking vs debt classification with formal exceptions
- Product code: only if main-chain bugs found

### Wave 3 — Real Provider + long-book acceptance (L3, user-approved)
- Execute approved L3 gates on Free four (and any in-scope modules)
- Product code: minimal fixes only

### Wave 4 — Installer RC → Stable (L4)
- **WB-6.4-120-RC** then **WB-6.5-120-STABLE** (or reconciled equivalents after Wave 0)
- Installer build：**YES**; Manual：**YES**; Real Provider：as gate requires

**Do not** resume heavy Contract-per-step process. Continue: Plan → ≤2 parallel Agents → Integration → Manual Gate; Freeze only when high-risk boundaries unfrozen.
