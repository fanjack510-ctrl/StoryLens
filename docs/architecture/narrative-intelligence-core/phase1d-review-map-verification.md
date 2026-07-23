# Phase 1D Review / Map Verification (Agent L)

Change: `CHG-20260723-029`  
Branch: `feature/narrative-phase1d-review-map`  
Baseline: `f79f199ea9dc53b8e92ae661baef3dc62007e905`

## Commands

```bash
# Backend focused
D:/Dstorylens/.venv/Scripts/python.exe -m pytest apps/api/tests/test_narrative_phase1d_review_map.py -q

# Frontend focused
cd apps/desktop && npx vitest run src/features/wholeBook/review/reviewMapPrototype.test.tsx src/features/narrativePattern

# Registry / hygiene
D:/Dstorylens/.venv/Scripts/python.exe scripts/version_manager.py check
D:/Dstorylens/.venv/Scripts/python.exe -c "from scripts.change_registry import *; ..."  # project-specific check
git diff --check
```

## Coverage map

| # | Case | Covered by |
|---|------|------------|
| 1–10 | Evidence read / hash / missing / stale / preview / deep link | `test_narrative_phase1d_review_map.py` |
| 11–17 | Review confirm/correct/reject/lock/expected_version/idempotency/no-evidence | same |
| 18–22 | Conflict list/compare/resolve/dismiss/blocking | same |
| 23–30 | Structure projection / canonical / candidates / views / limits / lazy / no DB write | same |
| 31–34 | SVG collapse/search/theme/keyboard | Vitest `reviewMapPrototype.test.tsx` + Agent C PatternMap tests |
| 35–39 | typecheck / focused tests / version_manager / change_registry / git diff --check | verification run |

## Forbidden (confirmed not done)

- Model calls, Pattern tables, migrations, VERSION bump, production build/publish/push
- Agent K result projection edits, formal result-page navigation
