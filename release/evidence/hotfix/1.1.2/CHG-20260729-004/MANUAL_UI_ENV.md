# MANUAL UI ENV — CHG-20260729-004

## Status

Ready for MG-CHG-20260729-004 MANUAL UI ACCEPTANCE

## Isolated runtime

| Item | Value |
|------|-------|
| Worktree | `D:\Dstorylens-wt-hotfix-1.1.2-journey-dimension-node-judgments` |
| Branch | `fix/1.1.2-journey-dimension-node-judgments` |
| Base HEAD | `bbcd6d7ac925303247599c9869e11780e4a7ca20` |
| Data dir | `%TEMP%\storylens-mg-chg004-dimension-judgments` |
| Database | `%TEMP%\storylens-mg-chg004-dimension-judgments\database\storylens-mg-chg004.db` |
| API | `http://127.0.0.1:18043` |
| Frontend | `http://127.0.0.1:1422` |
| Journey API | `http://127.0.0.1:18043/api/v1/reader-journey-runs/1` |
| Journey URL | `http://127.0.0.1:1422/books/1?chapter=1&journeyRun=1` |

## Runtime status (agent-prepared)

- API health: OK on `:18043`
- Frontend: OK on `:1422`
- Journey run 1: available (copied from CHG-003 Fake MG DB; FE derives dimension judgments at render)

## Fake / safety

- `STORYLENS_REAL_PROVIDER_ENABLED=0`
- `STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1`
- `STORYLENS_JOURNEY_FAKE_MODE=success`
- Formal AppData DB not used

## Manual focus

1. Open 剧情推进 — six nodes show plot short judgments  
2. Switch 阅读张力 — labels become tension semantics  
3. Switch 情绪强度 — emotion type/direction labels  
4. Switch 节奏速度 — accelerate/decelerate/stable labels; fit shows 合适/偏快/偏慢  
5. Fit under nodes independent of short judgment  
6. Tooltip + bottom axis sync; composite + 钩子回收 unchanged  
7. Stage bands `#E4F1E8` / `#F7EDD8` / `#E7EDF6` preserved  
8. Refresh — same journey remains

## Notes

Judgments are FE presentation derives; historical journeys need no re-analysis.
