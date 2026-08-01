# RC.2 Workflow Consistency Audit — CHG-20260729-011 / INC-20260729-005

## Start state

| Field | Value |
|-------|-------|
| Worktree | `D:\Dstorylens-wt-hotfix-1.1.2-chapter-workflow-consistency` |
| Branch | `fix/1.1.2-chapter-workflow-consistency` |
| Public HEAD (40) | `e59da1238eb2c509b4a05d7a401a6b5a1b2002ee` |
| git status | clean |
| v1.1.1 Tag SHA | `6f7d88c41f8006176fe77dd92bdb06cf1c6683e3` |
| VERSION | `1.1.2` |
| Forensic DB (read-only copy) | `D:\StoryLensIncident\INC-20260729-005-chapter-workflow-consistency\readonly-copy\database\storylens-rc2-forensic.db` |
| Formal DB writes this audit | **0** (sqlite backup `mode=ro`) |

## RC.2 installed acceptance

**FAILED** — release train must remain blocked until retest.

## Forensic facts (chapter_id=1301, analysis_run_id=4)

| Fact | Value |
|------|-------|
| Confirmed revision | **id=5**, revision_number=3, status=`confirmed` |
| Confirmed scene count | **6** (Scene ids 34–39, ordinals 1–6) |
| Superseded revision | id=4, revision_number=2, **16** scenes (ids 18–23 for ordinals 1–6 plus more) |
| Earlier superseded | id=3, revision_number=1 |
| Scenes on run 4 without revision filter | **22** (= 16 + 6) |
| Duplicate ordinals on run 4 | ordinals 1–6 each appear **twice** (e.g. ordinal 1 → ids `18,34`) |
| Journey run | id=3, `scene_revision_id=5`, `total_scene_count=6`, status=`succeeded` |
| Journey completed_scene_ids | `[34,35,36,37,38,39]` (raw DB ids surfaced in Tasks UI) |

**22 场景来源**：`GET /analysis-runs/{run_id}/scenes` / `build_run_results` 仅按 `created_by_run_id` 查询，把 superseded revision 的 16 行与 confirmed revision 的 6 行拼在一起。

**重复 S01/S02**：同一 `created_by_run_id` 上 rematerialize 不删除旧 Scene，ordinal 不唯一；列表用 `formatSceneDisplayLabel(ordinal)` → 多组 S01。

**内部 ID 暴露**：`TasksPage` / journey `completed_scene_ids_json` 直接渲染 `#34` 等主键。

## Code path answers (1–16)

1. **Confirmed Revision ID**：forensic `boundary_revisions.id=5`（章节 1301）。
2. **Confirmed scene count**：6。
3. **Journey Run bound revision**：`reader_journey_runs.id=3.scene_revision_id=5`。
4. **22 scenes source**：run `4` 下 revision `4`(16) + revision `5`(6)，无 revision 过滤的 Scene Result API。
5. **Duplicate S01/S02**：同 run 多代 Scene（ids 18↔34, 19↔35, …）。
6. **Missing filter**：`scene_results_service.build_run_results` / `GET .../chapters/{id}/scenes` / `GET .../analysis-runs/{id}/scenes` **缺少** `boundary_revision_id` / confirmed revision 过滤。
7. **「阅读旅程已中断」**：`resolveJourneyPageState` / `mapReaderJourneyStatusToUi` / gate `failed|interrupted` 文案；可与其他源并行。
8. **「正在生成阅读旅程」**：`mapChapterCompositionState` → `reader_journey_processing`；`ReaderJourneyProgressCard` 硬编码标题；banner。
9. **右侧进度面板**：`ChapterAnalysisProgressPanel` + composition / run progress，**不读**统一 presentation model。
10. **Task Center vs Chapter**：`discoverActiveChapterRun` / URL `analysisRun` / journey query 可能选不同 run；本事故章以 run4+journey3 为主，但 UI 状态机分裂即可造成冲突文案。
11. **混用**：Results 用 run 全量 Scene；Journey 用 revision 绑定 — **分裂事实源**。
12. **顶栏显隐**：`WorkspaceViewSwitcher` + `BookRoutePage` 的 `analysisAvailable` / `journeyAvailable` / `journeyInProgress`，**不读**统一 stage。
13. **「场景分析」标签**：`WorkspaceViewSwitcher` 固定 tab，承载结果/场景目录，不是用户主目标。
14. **中间空页**：`resolveSceneJourneyGate` kind=`need_confirm` 标题「阅读旅程尚未开始」+「去确认场景」；在 `source==="none"` 时挂载。
15. **确认场景 vs 阅读旅程**：Overflow/主 CTA「确认场景」与旅程 gate「去确认场景」指向同一 `view=scene-boundary-review`。
16. **钩子重复**：`HookPayoffTimeline` 同时渲染 blurb、summary_line、四项统计、场景轨标签、重要钩子卡；技术分数可进入诊断文案。

## Root cause classification (evidence-backed)

| Code | Applies? |
|------|----------|
| **A. MULTIPLE_CHAPTER_WORKFLOW_STATE_SOURCES** | **YES** — composition / pageState / gate / lifecycle / progress 并行 |
| **B. TERMINAL_STATE_NOT_PROPAGATED** | **YES** — parent `journey_running` / composition processing 可与 interrupted 主区共存 |
| **C. OLD_RUN_SELECTED_AS_CURRENT** | PARTIAL — URL/deep-link 可指向旧 journey；本事故主因是同 run 多 revision |
| **D. REVISION_FILTER_MISSING** | **YES** — Scene Result / 章节 scenes API |
| **E. SCENE_RESULT_CROSS_REVISION_CONTAMINATION** | **YES** — 16+6=22；重复 ordinal |
| **F. RAW_SCENE_ID_EXPOSED_AS_ORDINAL** | **YES** — Tasks / completed ids |
| **G. STATIC_NAVIGATION_IGNORES_STAGE** | **YES** |
| **H. DUPLICATE_ROUTE_GATE** | **YES** — need_confirm 中间跳板 |
| **I. MULTIPLE_PRIMARY_ACTIONS** | **YES** |
| **J. DUPLICATE_HOOK_PRESENTATION** | **YES** |
| K. OTHER | — |

## Fix direction (no product algorithm change)

1. Introduce **ChapterAnalysisPresentationV1** as single SSOT for shell/nav/CTA/status.
2. Bind Scene Result queries to **confirmed revision** (or journey `included_scene_ids`) without deleting historical Scene rows.
3. Stage-aware top nav; remove ordinary「场景分析」tab; redirect journey-before-confirm to confirmation.
4. Enforce interrupted vs running exclusivity via presentation priority.
5. Hook lens：一句总判断 + ≤3 问题卡 + 变化轨迹 + 一段洞察；分数/ID 进折叠技术详情。

## Constraints

- REAL PROVIDER CALLS: 0  
- FORMAL DATABASE WRITES: 0  
- No Build / Installer / Push / Tag / Release / VERSION bump  
