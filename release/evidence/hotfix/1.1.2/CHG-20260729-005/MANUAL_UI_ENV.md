# MANUAL UI ENV — CHG-20260729-005

## Status

Ready for MG-CHG-20260729-005 MANUAL UI ACCEPTANCE

## Isolated runtime

| Item | Value |
|------|-------|
| Worktree | `D:\Dstorylens-wt-hotfix-1.1.2-chapter-hook-simplification` |
| Branch | `fix/1.1.2-chapter-hook-simplification` |
| Base HEAD | `2e8ed1edaf7dc91933666f5e46f4b2bdb747407c` |
| Data dir | `%TEMP%\storylens-mg-chg005-hook-simplification` |
| Database | `%TEMP%\storylens-mg-chg005-hook-simplification\database\storylens-mg-chg005.db` |
| API | `http://127.0.0.1:18044` |
| Frontend | `http://127.0.0.1:1423` |
| Journey URL | `http://127.0.0.1:1423/books/1?chapter=1&journeyRun=1&lens=hook_payoff` |

## Fake / safety

- `STORYLENS_REAL_PROVIDER_ENABLED=0`
- `STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1`
- `STORYLENS_JOURNEY_FAKE_MODE=success`
- Formal AppData DB not used

## Manual focus

1. Tab still named **钩子回收**
2. Overview: 本章提出 / 本章回应 / 继续保留 / 章末牵引
3. Scene labels only: 提出疑问 / 加深悬念 / 给出回应 / 留到下章
4. Important questions readable (1–3); no internal IDs
5. 继续保留 not shown as failure / red unresolved risk
6. Other lenses unchanged; refresh keeps journey
