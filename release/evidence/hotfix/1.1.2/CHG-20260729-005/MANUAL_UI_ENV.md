# MANUAL UI ENV — CHG-20260729-005 (final)

## Status

Ready for MG-CHG-20260729-005 MANUAL UI ACCEPTANCE

## Isolated runtime

| Item | Value |
|------|-------|
| Worktree | `D:\Dstorylens-wt-hotfix-1.1.2-chapter-hook-simplification` |
| Branch | `fix/1.1.2-chapter-hook-simplification` |
| Public base HEAD | `2e8ed1edaf7dc91933666f5e46f4b2bdb747407c` |
| Data dir | `%TEMP%\storylens-mg-chg005-hook-simplification-final` |
| Database | `%TEMP%\storylens-mg-chg005-hook-simplification-final\database\storylens-mg-chg005-final.db` |
| API | `http://127.0.0.1:18044` |
| Frontend | `http://127.0.0.1:1423` |
| Journey API | `http://127.0.0.1:18044/api/v1/reader-journey-runs/1` |
| Journey URL | `http://127.0.0.1:1423/books/1?chapter=1&journeyRun=1&lens=hook_payoff` |

## Fake / safety

- `STORYLENS_REAL_PROVIDER_ENABLED=0`
- `STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1`
- `STORYLENS_JOURNEY_FAKE_MODE=success`
- `STORYLENS_ALLOWED_ORIGINS=http://127.0.0.1:1423`
- `VITE_API_BASE_URL=http://127.0.0.1:18044`
- Formal AppData DB not used
- 6-scene Fake fixture; not a real novel

## Manual focus

1. Tab still named **钩子回收**
2. Overview: 本章提出 / 本章回应 / 继续保留 / 章末牵引（无回收率）
3. Scene labels only: 提出疑问 / 加深悬念 / 给出回应 / 留到下章
4. Important questions 1–3 as reader questions; no Hook ID / smoke-fake
5. Dedicated 章末牵引 readable
6. Right panel 钩子洞察 switches with Scene
7. Ordinary mode: no large tech table
8. Developer mode: bottom 技术详情 default collapsed
9. Other lenses unchanged; Scene selection preserved; refresh keeps journey
