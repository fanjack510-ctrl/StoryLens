# MANUAL_UI_ENV — CHG-20260730-013

| Item | Value |
|---|---|
| DATABASE | `%TEMP%\storylens-mg-chg013-confirm-start\database\storylens-mg-chg013.db` |
| API | `http://127.0.0.1:18048` |
| FRONTEND | `http://127.0.0.1:1427` |
| REAL PROVIDER | OFF (`STORYLENS_REAL_PROVIDER_ENABLED=0`) |
| Formal DB | do not open / do not write |

## Fixture A — Confirm + Delayed Worker

URL (after seeding book/chapter in isolated DB): chapter journey progress after confirm.

Expected: brief「正在启动阅读旅程」→ auto analysis; no failed/interrupted; no Continue required.

## Fixture B — Recoverable Interrupted

URL: same chapter with claimed-then-interrupted journey.

Expected: one Continue → same Run → current journey progress; no scene-boundary-review dead end.

## Next

`MG-CHG-20260730-013 MANUAL UI ACCEPTANCE`
