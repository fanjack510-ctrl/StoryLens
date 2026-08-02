# AGENT_OWNERSHIP — WB-2.2 FREEZE

PARALLEL AGENTS：**2**  
Coding authorization：**BLOCKED until this freeze is committed and user authorizes implementation.**

## Agent 1 — Backend / Contract / Private / Pipeline / API / Fixtures

Exclusive ownership:

- `apps/api/app/narrative_core/services/chapter_functions_*.py`（output_contract_v2, mapper_v2, execution_materialization）
- `apps/api/app/narrative_core/services/whole_book_module_output_validator.py`（chapter_functions V2 hooks only）
- `apps/api/app/narrative_core/services/whole_book_provider_gateway.py`（chapter_functions paths only）
- `apps/api/app/narrative_core/services/whole_book_free_product_v1_service.py`（chapter_functions stage wiring）
- `apps/api/app/narrative_core/services/whole_book_product_capability_v1.py`（`chapter_functions` → available）
- `apps/api/app/routers/whole_book_free_product_router.py`（add chapter-functions routes）
- `apps/api/app/narrative_core/contracts/whole_book_contract_v1/constants.py`（stage code only）
- `apps/api/app/narrative_core/product_contract/module_results.py`（add `ChapterFunctionsResultV2`；keep Lab V1 DTO）
- Lab adapters/mappers for chapter_functions（hunk-limited；no Free SoT = Lab V1）
- Private: `modules/chapter_functions/**`, `prompt_packs/chapter_functions/**`, normalize/repair, batching tests
- Backend fixtures + `apps/api/tests/test_whole_book_wb22_*` / contract / empty-policy tests
- Migrations：**none**（DATABASE NOT REQUIRED）；if gap found → stop + new Change

## Agent 2 — Desktop / UI / Evidence / Vitest / Playwright

Exclusive ownership:

- `apps/desktop/src/components/wholeBookFree/chapterFunctions/**`（preferred new dir）
- `apps/desktop/src/services/wholeBookFreeProductApi.ts`（chapter-functions client + V2 types）
- `apps/desktop/src/services/wholeBookFreeProductStages.ts`（stage label only）
- Vitest / Playwright for module states + deeplink + pagination UX + layout
- Does **not** edit capability Python / Private engine

## Forbidden simultaneous edits

| File | Owner |
|---|---|
| `WholeBookFreeProductPage.tsx` | **Integration-only**（or Agent2 after Agent1 API landed；not parallel with Agent1） |
| `WholeBookFreeProductPage.module.css` | Integration / Agent2 sequential |
| `whole_book_product_capability_v1.py` | Agent1 only |
| `docs/whole-book/EXECUTION_REGISTRY.json` | Integration only |
| `release/changes/*`, `release/unreleased.json` | Integration only |

## MERGE ORDER

1. This Freeze（docs）committed  
2. User authorizes coding  
3. Agent1（contract + Private + API + fixtures）  
4. Agent2（UI）  
5. Integration + MG-WB-2.2  

## Ownership conflicts

**AGENT OWNERSHIP CONFLICTS：0**（Free page shell = Integration）.
