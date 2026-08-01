# MANUAL UI ENV — CHG-20260729-005 hook consistency retest

## Status

Ready for MG-CHG-20260729-005 MANUAL UI RETEST

## Isolated runtime

| Item | Value |
|------|-------|
| Worktree | `D:\Dstorylens-wt-hotfix-1.1.2-chapter-hook-simplification` |
| Branch | `fix/1.1.2-chapter-hook-simplification` |
| Start HEAD | `d0024432a55d9fd4e257d5b92581715c735e0ce1` |
| Data dir | `%TEMP%\storylens-mg-chg005-hook-consistency` |
| Database | `%TEMP%\storylens-mg-chg005-hook-consistency\database\storylens-mg-chg005-consistency.db` |
| API | `http://127.0.0.1:18044` |
| Frontend | `http://127.0.0.1:1423` |

## URLs

NO HOOK JOURNEY URL (default Fixture A — Fake / smoke-fake → uncertain)：  
http://127.0.0.1:1423/books/1?chapter=1&journeyRun=1&lens=hook_payoff

RELIABLE HOOK JOURNEY URL：  
Presentation Fixture B covered by automated vitest (`chg005FixtureBReliableHooks`). Live Fake cannot emit reliable reader questions without changing Fake/algorithm; open NO HOOK URL for the reported defect retest.

## Fake / safety

- Real Provider OFF
- Smoke Fake ON
- CORS `http://127.0.0.1:1423`
- `VITE_API_BASE_URL=http://127.0.0.1:18044`
- Formal AppData DB not used

## Retest focus (Fixture A)

1. Chapter shows weaker/empty hook copy — not failure
2. Overview 0 / 0 / 0 / 无法判断 or 暂无
3. S05 band label is `—` — **not** `明确回应`
4. Scene node labels blank / `—`
5. Right insight matches chapter mode (weaker or none copy)
6. No `未发现明显异常` / `回收率` / `smoke-fake` on ordinary Hook page
