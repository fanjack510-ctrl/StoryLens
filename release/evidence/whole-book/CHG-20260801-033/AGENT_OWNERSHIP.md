# AGENT_OWNERSHIP

PARALLEL AGENTS：**2**

## Agent 1 — Backend / Contract / Private

Exclusive ownership:

- `apps/api/app/narrative_core/services/structure_stages_*.py` (incl. execution_materialization, output_contract_v2, mapper_v2)
- `apps/api/app/narrative_core/services/whole_book_provider_gateway.py` (structure paths only; coordinate if shared)
- `apps/api/app/narrative_core/services/whole_book_module_output_validator.py`
- `apps/api/app/narrative_core/services/whole_book_free_product_v1_service.py`
- `apps/api/app/narrative_core/services/whole_book_product_capability_v1.py`
- `apps/api/app/routers/whole_book_free_product_router.py` (add structure route)
- `apps/api/app/narrative_core/contracts/whole_book_contract_v1/constants.py` (stage codes)
- `apps/api/app/narrative_core/product_contract/module_results.py` (V2 only as needed)
- Lab selective ports: runtime/executor/adapters (**hunk-limited**)
- Private: `citation/structure_*.py`, `modules/structure_stages/**`, related tests
- Backend fixtures + `apps/api/tests/test_*structure*` / free product API tests
- Migrations: **none expected**; if later required → Agent1 only

## Agent 2 — Desktop / UI / Evidence

Exclusive ownership:

- New components under `apps/desktop/src/components/wholeBookFree/structure/**` (preferred)
- `apps/desktop/src/services/wholeBookFreeProductApi.ts` (structure client methods/types)
- `apps/desktop/src/services/wholeBookFreeProductStages.ts` (stage labels only)
- Vitest / Playwright for structure UI + deeplink + layout
- Does **not** edit capability registry Python

## Forbidden simultaneous edits

| File | Owner |
|---|---|
| `WholeBookFreeProductPage.tsx` | **Integration-only** (or Agent2 after Agent1 API freeze; not parallel with Agent1) |
| `WholeBookFreeProductPage.module.css` | Integration / Agent2 sequential |
| `whole_book_product_capability_v1.py` | Agent1 only |
| `docs/whole-book/EXECUTION_REGISTRY.json` | Integration only |
| `release/changes/*`, `release/unreleased.json` | Integration only |
| Shared OpenAPI/typegen outputs (if any) | Integration only |

## Integration-only

- Wire Free page panels to Agent2 components  
- Final capability↔UI consistency  
- Full regression matrix execution  
- CHG/evidence registry updates for implementation Change  
- Resolve CONFLICT_REWRITE_REQUIRED Lab hunks if Agent1 blocked  

## Ownership conflicts

**AGENT OWNERSHIP CONFLICTS：0** (with Integration owning the Free page shell).
