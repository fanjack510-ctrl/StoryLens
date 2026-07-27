# CHG-20260727-020 Manual Source Verification

**Status:** verified (zero-cost + fixture; RC9 packaging gate)  
**Step:** 2.9-RC9-GATE-AND-BUILD  
**Date:** 2026-07-27  

## Acceptance evidence

| Criterion | Result |
|-----------|--------|
| Run #4 Journey succeeded 8/8 + chapter summary (AppData WAL backup, read-only) | PASS (`verify-output.txt`) |
| Active overrides stale failed Journey GET | PASS (Vitest + pure-state checks) |
| Completed + final artifact overrides stale failure | PASS |
| Out-of-order failed response cannot overwrite newer running state | PASS |
| Old attempt isolation by journey id | PASS |
| Temporary API error shows reconnect semantics (no 重新生成) | PASS |
| Terminal failure still shows 阅读旅程生成失败 when truly terminal | PASS |
| Real Provider calls / new runs / new journey tasks | 0 |
| Targeted Vitest (resolveJourneyPageState + BookRoute + composition + lifecycle) | PASS |
| TypeScript typecheck | PASS |

## Non-goals / still blocked

- CHG-20260727-018 stable 1.1.0 remains BLOCKED pending RC9 install acceptance.
- RC8 packaging is superseded by RC9 (stale Journey progress failure fixed in CHG-020).
- This verification does not Push / Tag / Release / build formal 1.1.0.

## Artifacts

- `verify-journey-progress-state.ps1`
- `verify-output.txt`
- Primary fix commit: `4167b1be04f9c26285f033482155c91467533df2`
