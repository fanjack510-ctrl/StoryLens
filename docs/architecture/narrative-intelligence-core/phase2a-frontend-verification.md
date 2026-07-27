# Phase 2A Frontend Verification (Agent N)

**Change:** CHG-20260723-033
**Baseline:** `1e8112f0de5a0c37085023ca75747555514f3b05`
**VERSION:** 1.0.5 (unchanged)

## Commands

```text
cd apps/desktop
npm run typecheck
npx vitest run src/features/wholeBook/runShell/__tests__
python scripts/version_manager.py check
python scripts/change_registry.py check
git diff --check
```

## Results (local)

| Check | Result |
|-------|--------|
| typecheck | PASS |
| focused Vitest (`runShell/__tests__`) | 29 passed |
| version_manager check | (recorded at commit) |
| change_registry check | (recorded at commit) |
| git diff --check | (recorded at commit) |

## Coverage map (task §十二)

| # | Item | Covered by |
|---|------|------------|
| 1–9 | Client create/get/stages/pause/resume/cancel/retry/marker/no formal API | `mockWholeBookRunClient.test.ts` |
| 10–14 | Lab disabled / production hide / mock badge / duplicate / double-click | `WholeBookMockRunLab.test.tsx` |
| 15–22 | Polling running/paused/terminal/visibility/backoff/stale/unmount/network | `mockRunPollingController.test.ts` |
| 23–27 | allowed_actions / Pause / Resume / Retry / Cancel confirm | `WholeBookMockRunLab.test.tsx` (controls) |
| 28–33 | partial / candidate / cancelled / interrupted / Evidence / Structure Map | Partial results tests |
| 34–36 | error presentation / theme / keyboard | Lab + error tests |
| 37–41 | typecheck / vitest / version_manager / change_registry / diff --check | this doc |

## No formal entry proof

- `src/app/router.tsx` does not import `WholeBookMockRunLab` or `/dev/whole-book-mock-run-lab`.
- `RUN_CREATE_ENABLED_IN_CLIENT === false`.
- Client `formalCreatePath` never invoked by Lab client.

## Forbidden (confirmed not done)

Backend edits · formal nav · formal Run API · WebSocket · VERSION bump · release/unreleased.json · production/Windows build · publish · push · stash restore.
