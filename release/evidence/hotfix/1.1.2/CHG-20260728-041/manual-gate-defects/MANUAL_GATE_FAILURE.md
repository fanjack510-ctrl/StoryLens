# MANUAL_GATE_FAILURE

- CHANGE: CHG-20260728-041
- GATE: MG-CHG-20260728-041
- Verdict: FAILED
- Public HEAD: 56226266e3bbfa935575ae61dd18c2e80ba7e612
- Isolated DB: `%TEMP%\storylens-mg-chg041\database\storylens-mg-chg041.db`

## User-visible failures
1. Entered scene editor via 阅读旅程 / vague「继续确认场景」
2. Confirm buttons appeared unresponsive or showed raw `SCENE_REVISION_CONCURRENT_MODIFICATION`
3. After first successful confirm, repeated confirm → HTTP 409
4. No loading / success / conflict recovery UX

## Evidence files
- ETAG_FAILURE_TRACE.json
- NAVIGATION_FAILURE.md
- DB_REVISIONS.json
- OVERVIEW_SANITIZED.json (if present)
- api.out.log excerpt under Temp MG logs
