# Phase 1D Agent J — Run UX Verification

Change: `CHG-20260723-027`

## Checklist mapping

| # | Requirement | Evidence |
|---|-------------|----------|
| 1 | Preflight client success | `preflightClient.test.ts` |
| 2 | Network failure | `preflightClient.test.ts` |
| 3 | Fail-closed | `preflightClient.test.ts` + failClosed model |
| 4 | `run_creation_enabled=false` | client + mapper + UI |
| 5 | Native select | `preflightView.test.tsx` |
| 6 | Enhanced select + coverage | `preflightView.test.tsx` |
| 7 | Unsupported mode disabled | `preflightView.test.tsx` |
| 8 | 11 modules | `preflightView.test.tsx` |
| 9 | Auto dependency display | module selector + stage plan |
| 10 | Required dependency locked | `preflightView.test.tsx` |
| 11 | Module/Stage separation | `preflightView.test.tsx` |
| 12 | Blocking reasons | PreflightView test |
| 13 | Start disabled | PreflightView + lab |
| 14 | No force start | queryByTestId / 强制启动 |
| 15 | Run status | `runProgress.test.tsx` |
| 16 | allowed_actions | fixture consumption |
| 17 | pause | action bar + adapter |
| 18 | resume | adapter test |
| 19 | retry | failed stage only |
| 20 | cancel confirm | action bar |
| 21 | partial result | notice + failed fixture |
| 22 | failed stage | fixture + UI |
| 23 | interrupted | distinct from failed |
| 24 | light/dark | lab theme toggle |
| 25 | keyboard | focus tests |
| 26 | DTO guard | `dtoGuardTheme.test.tsx` |
| 27 | typecheck | `npm run typecheck` |
| 28 | focused Vitest | runUx `__tests__` |
| 29 | version_manager check | script |
| 30 | change_registry check | script |
| 31 | `git diff --check` | script |

## Commands

```powershell
cd D:\Dstorylens-wt-narrative-run-ux\apps\desktop
npm run typecheck
npx vitest run src/features/wholeBook/runUx

cd D:\Dstorylens-wt-narrative-run-ux
python scripts/version_manager.py check
python scripts/change_registry.py check
git diff --check
```

## No real start proof

- Start button `disabled` + `data-force-start="false"`
- `RUN_CREATE_ENABLED_IN_CLIENT === false`
- Client only POSTs `.../preflight`
- Mock action adapter never fetches production run control URLs
