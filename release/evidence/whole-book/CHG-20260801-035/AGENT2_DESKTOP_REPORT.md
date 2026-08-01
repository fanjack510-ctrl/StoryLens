# WB-2.1 AGENT 2 DESKTOP REPORT

CHANGE：CHG-20260801-035

PUBLIC BASE HEAD：710d05ad7d759160c9bb09b860fc395f9af6d005

CANONICAL CONTRACT：V2 / StructureStagesResultV2

CONTRACT VERSION：2.0.0 / wire `v2`

## Implementation summary

- Free module `structure` status: `planned` → `available`
- Product client: `GET /api/v1/whole-book/runs/{run_id}/structure`
- UI: `StructureStagesPanel` (overview / variable stages / turning points / states)
- Evidence: Wave D deep link + `returnModule=structure` (no fuzzy fallback, no evidence_map)
- Fixtures A–L under `apps/desktop/src/components/wholeBookFree/structure/fixtures/`
- Vitest + Playwright (route mock); Typecheck PASS

## Commands

```text
cd apps/desktop
npm run typecheck
npm test -- src/pages/wholeBookFreeStructure.test.tsx src/services/structureStagesResultV2.test.ts src/pages/wholeBookFreeProduct.test.tsx src/pages/wholeBookFreeProduct.layout.test.tsx
npm run test:e2e:wb21-structure
```

## Status

CHANGE STATUS：tested  
READY FOR INTEGRATION：YES  
PROTECTED WIP MODIFIED：NO  
REAL PROVIDER CALLS：0  
FORMAL DATABASE WRITES：0  
