# MANUAL_UI_ENV — CHG-20260729-011

## Status

Ready for MG-CHG-20260729-011 MANUAL UI ACCEPTANCE

## Isolated runtime

| Item | Value |
|------|--------|
| Worktree | `D:\Dstorylens-wt-hotfix-1.1.2-chapter-workflow-consistency` |
| Branch | `fix/1.1.2-chapter-workflow-consistency` |
| Public HEAD (base) | `e59da1238eb2c509b4a05d7a401a6b5a1b2002ee` |
| Data dir | `%TEMP%\storylens-mg-chg011-workflow-consistency` |
| DATABASE | `%TEMP%\storylens-mg-chg011-workflow-consistency\database\storylens-mg-chg011.db` |
| API | `http://127.0.0.1:18047` |
| FRONTEND | `http://127.0.0.1:1426` |
| TASK CENTER | `http://127.0.0.1:1426/tasks` |

## Case URLs

| Case | URL |
|------|-----|
| REVISION 22-TO-6 | http://127.0.0.1:1426/books/1?chapter=1&analysisRun=2&view=result |
| INTERRUPTED | http://127.0.0.1:1426/books/1?chapter=2&analysisRun=3&journeyRun=2 |
| AWAITING CONFIRMATION | http://127.0.0.1:1426/books/1?chapter=3&analysisRun=4&view=scene-boundary-review |
| RUNNING | http://127.0.0.1:1426/books/1?chapter=4&analysisRun=5&journeyRun=3 |
| SUCCEEDED | http://127.0.0.1:1426/books/1?chapter=5&analysisRun=6&journeyRun=4&view=result |
| HOOK EMPTY | http://127.0.0.1:1426/books/1?chapter=5&journeyRun=4&lens=hook_payoff |
| HOOK RICH | http://127.0.0.1:1426/books/1?chapter=6&analysisRun=7&journeyRun=5&view=result&tab=reader-journey&lens=hook_payoff |

## Hook Rich live fixture

| Field | Value |
|-------|--------|
| Source | `chg005FixtureBReliableHooks` facts persisted via `seed_mg_chg011_hook_rich.py` |
| Chapter | 6 |
| Analysis run | 7 |
| Journey run | 5 (succeeded) |
| Confirmed revision | 9 |
| Scene count | 6 |
| Provider calls | 0 |

## API restart loop

1. Record API PID
2. Stop isolation API
3. Restart against same DB
4. Run `refresh_mg_after_api_boot.py`
5. Re-run `precheck_hook_rich.py` + `precheck_hook_rich_presentation.ts`

Evidence: `API_RESTART_LOOP.json`, `HOOK_RICH_PRECHECK.json`, `HOOK_RICH_PRESENTATION_PRECHECK.json`

## Fake / safety

- Real Provider OFF
- Formal AppData DB not used
- REAL PROVIDER CALLS: **0**
- FORMAL DATABASE WRITES: **0**

## Manual focus

1. Hook Rich live page: one verdict, 读者最想知道 1–3 cards, trajectory of change nodes, scene insight, tech details collapsed
2. Interrupted page: 已中断 only (not 正在生成)
3. Revision 22→6: ordinary UI shows 6 only
4. Awaiting confirmation: 确认场景 primary; no 阅读旅程 tab
5. After browser refresh / API restart: same IDs and counts
