# FINAL RETEST PLAN — CHG-20260728-041 Round 2

## Environment (pinned commit)

| Item | Value |
|------|-------|
| PUBLIC HEAD | `084063eb8876231ae39b3c249142bd7ccb6ec3f5` |
| API | http://127.0.0.1:18041 |
| Frontend | http://127.0.0.1:1421 |
| Database | `%TEMP%\storylens-mg-chg041-final-retest\database\storylens-mg-chg041-final.db` |
| Fake Provider | ENABLED |
| Real Provider | DISABLED |
| Formal AppData | unused |

## Entry

http://127.0.0.1:1421/books/1?view=scene-boundary-review&chapter=1&analysisRun=1

## Main flow (must pass)

1. Open scene boundary review (awaiting confirmation on AI model revision).
2. Adjust one boundary (or inclusion).
3. Click **确认并生成阅读旅程** (Confirm+Start).
4. Expect new `journey_run_id` and auto navigation to Reader Journey (`view=result&tab=reader-journey&journeyRun=…`).
5. Do **not** see a second start CTA that re-enters confirmation.
6. Do **not** see “请先确认场景” after successful Confirm+Start.
7. Optional: Confirm-only path; no-change reconfirm must not create another revision.

## Stop / start (this env only)

- `%TEMP%\storylens-mg-chg041-final-retest\stop_final_retest.ps1`
- `%TEMP%\storylens-mg-chg041-final-retest\start_final_retest.ps1`

## Out of scope

- Marking CHG-041 verified
- Merge / Push / Build / VERSION
- Real Provider
