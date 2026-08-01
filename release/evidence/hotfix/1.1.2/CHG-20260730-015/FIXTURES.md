# FIXTURES — MG-CHG-20260730-015

Isolated DB: `%TEMP%\storylens-mg-chg015-rc4-failure\database\storylens-mg-chg015.db`

Seed: `seed_mg_chg015_fixtures.py`  
Probe: `probe_mg_chg015_preacceptance.py`  
Manifest: `FIXTURE_MANIFEST.json`

## A — Scene analysis structural failure

- URL: http://127.0.0.1:1428/books/1?chapter=1&analysisRun=1&view=progress
- Analysis Run: 1
- Journey Run: none
- Expected: 场景分析未完成；0/3；Journey 未启动；无中断/暂停

## B — Journey synthesis failure

- URL: http://127.0.0.1:1428/books/1?chapter=2&analysisRun=2&journeyRun=1&view=progress
- Analysis Run: 2 / Journey Run: 1
- Expected: 阅读旅程整合失败；Scene 3/3 完成；失败阶段 reader_journey_chapter_synthesis

## C — Recoverable interrupt（原 Fixture，已污染 — 仅作审计）

- URL: http://127.0.0.1:1428/books/1?chapter=3&analysisRun=3&journeyRun=2&view=progress
- Analysis Run: 3 / Journey Run: 2（另有污染 sibling Journey 5 succeeded）
- 审计: `manual-gate-recoverable-defect/RECOVERABLE_FIXTURE_STATE_AUDIT.md`
- **不得**作为合法 Recoverable 验收

## C2 — Legal Recoverable interrupt（人工复测用）

- URL: http://127.0.0.1:1428/books/1?chapter=6&analysisRun=6&journeyRun=6&view=progress
- Analysis Run: 6 / Journey Run: 6 / Revision: 8
- Expected: 阅读旅程已中断；Scene 完成；Journey 未完成；主按钮「继续分析」；Continue 恢复同一 Journey Run 6
- Continue same-run proof: `manual-gate-recoverable-defect/CONTINUE_SAME_RUN_PROOF.json`（随后已 re-arm 为 interrupted）

## D — Success wait gate (manual)

- URL: http://127.0.0.1:1428/books/1?chapter=4&analysisRun=4&view=scene-boundary-review
- Analysis Run: 4
- AI scenes: 2 → draft: 3
- Action: 点击「确认这 3 个场景并开始分析」
- Expected: WAITING_SCENE_ANALYSIS → 补齐 3 Scene → 自动 Journey → 成功；无需 Continue

## D-auto — Wait gate HTTP probe (not for manual click)

- Chapter 5 / Analysis Run 5 / Journey Run 3
- AUTO_PREACCEPTANCE: PASS（waiting_seen=true，无 SCENE_ANALYSIS_INCOMPLETE，journey_start_count=1）
