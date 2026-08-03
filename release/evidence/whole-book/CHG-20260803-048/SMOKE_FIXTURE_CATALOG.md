# SMOKE_FIXTURE_CATALOG — CHG-20260803-048

## Source
| Item | Value |
|---|---|
| Seed script | `apps/api/scripts_seed_wb22_integration.py` |
| Seed path (assert) | `%TEMP%\storylens-wb22-integration-v120-e2e\` |
| Manual smoke root | `%TEMP%\storylens-v120-e2e\` |
| DB | `C:\Users\msi\AppData\Local\Temp\storylens-v120-e2e\storylens_v120_e2e.db` |
| Fixtures JSON | `%TEMP%\storylens-v120-e2e\MANUAL_FIXTURES.json` |
| API | http://127.0.0.1:8007 |
| UI | http://127.0.0.1:1427 |

Seeded into `storylens-wb22-integration*` path (seed assert), then SQLite `backup()` checkpointed into `storylens-v120-e2e` (full books 1–16; do not copy `.db` alone without WAL checkpoint).

Real provider: **disabled**. Fixture origin / 测试数据 banner required.

## Required MG entry map (section 九)

| Entry | Catalog key | book_id | run_id | URL |
|---|---|---|---|---|
| 1 四模块同一 Run | `cf_available` / regressions | 1 | 1 | `/books/1/whole-book?module=overview&run=1` (+ characters/structure/CF) |
| 2 Cost / Consent | `cost_consent` | 16 | — | `/books/16/whole-book` |
| 3 Revision 旧 Consent 失效 | (API wb221) | — | — | directed pytest; UI: re-prepare after text edit |
| 4 Pause | (API wb221) | — | — | directed pytest |
| 5 Resume | (API wb221) | — | — | directed pytest |
| 6 Cancel | `canceled` | 8 | 8 | `/books/8/whole-book?module=chapter_functions&run=8` |
| 7 Restart Recovery | (API wb221) | — | — | directed pytest |
| 8 completed terminal | `cf_available` | 1 | 1 | CF available URL |
| 9 failed terminal | `cf_failed` | 7 | 7 | `/books/7/whole-book?module=chapter_functions&run=7` |
| 10 canceled terminal | `canceled` | 8 | 8 | see Cancel |
| 11 conflict | `conflict` | 9 | 9 | `/books/9/whole-book?module=chapter_functions&run=9` |
| 12 Overview Evidence | `regression_overview` | 1 | 1 | `module=overview&run=1` |
| 13 Characters/Events Evidence | `regression_characters` | 1 | 1 | `module=characters_events&run=1` |
| 14 Structure Evidence | `regression_structure` | 1 | 1 | `module=structure&run=1` |
| 15 CF Evidence | `cf_evidence` | 10 | 10 | `/books/10/whole-book?module=chapter_functions&run=10` |
| 16 CF restore | filters/detail | 1 | 1 | `cfFunction` / `cfStatus` / `cfChapter` URLs |
| 17 Provider disabled | (API wb221) | — | — | directed pytest |
| 18 Fixture Preview | banner on fixture pages | 1+ | — | Fixture banner PRESENT (DOM) |
| 19 1366 | layout | 1 | 1 | DOM viewport check |
| 20 1920 | layout | 1 | 1 | DOM viewport check |

## Full catalog keys
22 fixture entries (A–M variants + filters + cost_consent + three regressions). See `MANUAL_FIXTURES.json`.
