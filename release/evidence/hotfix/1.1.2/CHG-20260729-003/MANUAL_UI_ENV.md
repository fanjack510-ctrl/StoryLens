# MANUAL UI ENV — CHG-20260729-003

## Status

Ready for MG-CHG-20260729-003 MANUAL UI ACCEPTANCE

## Isolated runtime

| Item | Value |
|------|-------|
| Worktree | `D:\Dstorylens-wt-hotfix-1.1.2-comprehensive-reading-curve` |
| Branch | `fix/1.1.2-comprehensive-reading-curve` |
| Data dir | `%TEMP%\storylens-mg-chg003-comprehensive` |
| Database | `%TEMP%\storylens-mg-chg003-comprehensive\database\storylens-mg-chg003.db` |
| API | `http://127.0.0.1:18042` |
| Frontend | `http://127.0.0.1:1421` |
| Journey URL | `http://127.0.0.1:1421/books/1?chapter=1&journeyRun=1` |

## Fake / safety

- `STORYLENS_REAL_PROVIDER_ENABLED=0`
- `STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1`
- `STORYLENS_JOURNEY_FAKE_MODE=success`
- Formal AppData DB not used

## Notes

Open 查看分析结果 → 阅读旅程 → 综合阅读. Confirm stage judgments, fit under points, short labels, key nodes, and right-panel insight without double「综合阅读：」prefix.
