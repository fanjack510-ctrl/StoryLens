# WB-2.2 AGENT OWNERSHIP（planning）

PARALLEL AGENTS：**2**（after Pre-Implementation Freeze）

## Agent 1 — Backend / Contract / Private / Pipeline / API / Fixture

Exclusive ownership:

- `structure`-style new files: `whole_book_*chapter_functions*`, output contract, mapper, materialization
- `constants.py` stage codes（chapter_functions only）
- `whole_book_product_capability_v1.py`（chapter_functions → available）
- `whole_book_free_product_router.py`（add route only）
- `module_results.py` / V2 DTO if freeze requires
- Private: `modules/chapter_functions/**`, `prompt_packs/chapter_functions/**`, validation/repair
- Backend fixtures + `test_whole_book_wb22_*` / contract tests
- Migrations: **none expected** unless freeze says otherwise → Agent1 only

## Agent 2 — Desktop / UI / Evidence / Vitest / Playwright

Exclusive ownership:

- `apps/desktop/src/components/wholeBookFree/chapterFunctions/**`（preferred new dir）
- `wholeBookFreeProductApi.ts`（chapter functions client）
- Vitest / Playwright for module + deeplink + layout
- Does **not** edit capability Python

## Shared / Integration-only

| File | Owner |
|---|---|
| `WholeBookFreeProductPage.tsx` | **Integration-only**（or Agent2 after API freeze；not parallel with Agent1） |
| `EXECUTION_REGISTRY.json` | Integration only |
| `release/changes/*`, `release/unreleased.json` | Integration only |

## MERGE ORDER

1. Pre-Implementation Freeze（docs）  
2. Agent1（contract+API+fixture+private）  
3. Agent2（UI types/panels）  
4. Integration  
5. MG-WB-2.2  

## Coding authorization

**BLOCKED** until Freeze resolves：Contract / Empty policy / DB / API / WB-2.1 context relation.
