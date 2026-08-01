# MANUAL UI ENV — MG-CHG-20260730-015

STATUS：READY FOR RECOVERABLE RETEST（未标记 verified）

PUBLIC HEAD：
f4560b19bc57d771e8a1baf0862b8bf1084a6347

（本地未提交产品修复 + 证据；PUBLIC CLEAN = NO）

DATABASE：
%TEMP%\storylens-mg-chg015-rc4-failure\database\storylens-mg-chg015.db

API：
http://127.0.0.1:18049

FRONTEND：
http://127.0.0.1:1428

ENV：
STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1
STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL=0
STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_DELAY_SECONDS=4
STORYLENS_JOURNEY_FAKE_MODE=success
STORYLENS_REAL_PROVIDER_ENABLED=0
STORYLENS_APP_PORT=18049
VITE_API_BASE_URL=http://127.0.0.1:18049

FAKE PROVIDER：ON
REAL PROVIDER：OFF
EXTERNAL PROVIDER CALLS：0
FORMAL DATABASE WRITES：0

## Live Fixture URLs

SCENE FAILURE：
http://127.0.0.1:1428/books/1?chapter=1&analysisRun=1&view=progress

SYNTHESIS FAILURE：
http://127.0.0.1:1428/books/1?chapter=2&analysisRun=2&journeyRun=1&view=progress

RECOVERABLE INTERRUPTED（**C2 合法 Fixture — 请用此 URL 复测**）：
http://127.0.0.1:1428/books/1?chapter=6&analysisRun=6&journeyRun=6&view=progress

ORIGINAL C（污染证据保留，勿作为合法 Recoverable 验收）：
http://127.0.0.1:1428/books/1?chapter=3&analysisRun=3&journeyRun=2&view=progress

SUCCESS（人工确认 2→3 场景；勿点自动探针第 5 章）：
http://127.0.0.1:1428/books/1?chapter=4&analysisRun=4&view=scene-boundary-review

## IDs

| Fixture | Analysis Run | Journey Run | Notes |
|---------|--------------|-------------|-------|
| A Scene failure | 1 | — | 0/3 STRUCTURAL_VALIDATION_FAILED |
| B Synthesis failure | 2 | 1 | 3/3 + JOURNEY_SYNTHESIS_FAILED |
| C Recoverable (contaminated) | 3 | 2 (+5 sibling) | 冻结审计；JR5 succeeded 污染 |
| **C2 Legal Recoverable** | **6** | **6** | JOURNEY_INTERRUPTED / can_resume / single journey |
| D Success (manual) | 4 | — | draft 3 scenes awaiting confirm |
| D-auto (probe only) | 5 | 3 | wait-gate auto PASS |

## C2 初始页必须看到

- 标题：阅读旅程已中断
- 主按钮：继续分析
- 不出现：分析已暂停 / 阅读旅程已完成 / 修复并继续 / 右侧恢复面板重试

缺陷审计：
`release/evidence/hotfix/1.1.2/CHG-20260730-015/manual-gate-recoverable-defect/RECOVERABLE_FIXTURE_STATE_AUDIT.md`

NEXT：
MG-CHG-20260730-015 RECOVERABLE FIXTURE RETEST
