# docs/48｜Single-Chapter Journey Template Governance（Phase 1D-A）

**版本：** Reader Journey Template v2.7（与 UI Final Baseline v2.7 对齐）  
**前置：** Reader Journey UI Final Freeze v2.7 已通过  
**范围：** 单章节旅程模板统一治理与传播认证（只读审计 + 测试证明）

## 1. 目标

证明：

1. 所有书的所有单章节旅程结果共用同一个 v2.7 模板；
2. Books 与 Standalone 路由只是适配层，不复制模板；
3. 模板经受控 Change Package 升级后，所有章节自动同步；
4. 不需要逐书、逐章改 UI；
5. UI 模板变化不要求重新运行 AnalysisRun / ReaderJourneyRun，也不要求调用模型。

本阶段**不**开发新 UI，**不**调用真实模型，**不**修改 v2.7 冻结生产文件。

## 2. Canonical Template 入口

| 角色 | 路径 |
|------|------|
| Canonical entry | `apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx` |
| Composition shell | `apps/desktop/src/components/readerJourney/ReaderJourneySyncWorkspace.tsx` |
| UI Final Baseline | `reader-journey-ui-final-v2.7` |

权威版本字段：`audits/.../reader-journey-ui-final-freeze-v2.7.json` 的 `version: "2.7"`。

只读模板描述：`audits/mvp-functional-baseline-v1/single-chapter-journey-template-v2.7.json`。

## 3. 路由适配链

### Books

```
/books/{bookId}?chapter=...&analysisRun=...&view=result&resultTab=reader-journey
  → BookRoutePage
  → EmbeddedAnalysisResultShell
  → AnalysisResultRouteAdapter
  → AnalysisResultsPage
  → ReaderJourneySyncWorkspace
  → ReaderJourneyWorkspace
```

### Standalone

```
/analysis-runs/{runId}/results?tab=reader-journey
  → AnalysisResultsShellPage
  → AnalysisResultsPage
  → ReaderJourneySyncWorkspace
  → ReaderJourneyWorkspace
```

两条链最终挂载**同一个** `ReaderJourneyWorkspace`。生产旅程模板入口数量 = **1**。

## 4. 审计结论摘要

| 问题 | 结论 |
|------|------|
| 是否同一 Workspace | 是 |
| 是否存在第二套生产旅程页 | 否（`JourneyOverviewModes.tsx` 为未引用遗留文件，非入口） |
| 是否复制模板 | 否 |
| book / chapter / Run #55 生产特例 | 无（测试可引用 Run #55） |
| Scene/Phase 数量写死 | 生产布局无写死；数量来自 visualization 数据 |
| Books vs Standalone 不同模板 DOM | 否（骨架一致） |
| 未纳入 v2.7 freeze 的生产依赖 | 路由壳与 `AnalysisResultsPage` 为适配/结果组合层，不复制模板 |

## 5. 模板版本单一来源

- **权威来源：** Final Freeze Manifest `version` / `baseline_name`
- 分散出现位置：docs、gate scripts、audit JSON、少量注释/测试标题
- 本阶段**不**越过 Final Freeze 重构生产代码；漂移风险记录于 conformance report

## 6. 传播规则

未来 UI 变更必须新建 Change Package：

`reader-journey-ui-change-<version>.json`

禁止原地覆盖 v2.7 Manifest。升级 canonical entry 后，所有章节自动使用新模板；章节 JSON **不包含**独立页面模板。

## 7. 门禁

```powershell
.\.venv\Scripts\python.exe .\scripts\check_single_chapter_journey_template.py
.\.venv\Scripts\python.exe .\scripts\check_reader_journey_ui_freeze.py
```

相关测试：`phase_1da_single_chapter_journey_template_governance.test.tsx`  
一致性报告：`audits/mvp-functional-baseline-v1/single-chapter-template-conformance-report-v2.7.json`

## 8. 明确结论

**所有单章节旅程结果统一使用 Reader Journey Template v2.7。**

模板变化通过受控版本升级自动作用于所有章节。

章节数据不包含独立页面模板。

UI 模板变化不要求重新调用模型。
