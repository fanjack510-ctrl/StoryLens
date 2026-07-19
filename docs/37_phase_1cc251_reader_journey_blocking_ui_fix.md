# docs/37｜Phase 1C-C.2.5.1 Reader Journey Blocking UI Fix

**阶段：** 曲线总览标签遮挡与 PNG 导出无反馈的最小缺陷修复（展示层）  
**非目标：** 不改分析数据、公式、选择语义、Scroll Spy、Pipeline、Schema；不调用真实模型；不新建 Run。

## 1. 标签遮挡根因

1. Metric 工具栏嵌在 `.journey-curve-section` 内，该容器 `min-height: 260px` + `overflow: hidden` + 纵向 flex，与 260px 曲线争抢同一盒子，窄/矮视口下按钮被裁切并压住曲线。
2. `.journey-overview-curve` 使用 `grid-template-rows: auto auto auto minmax(260px,1fr)`，但 DOM 仅 3 个子节点（summary / phase / curve-section），第 4 行空置，指标层未独立成行。
3. 同一节点同时带 `journey-summary-cards` 与 `journey-metric-strip`，后者 `display:flex` 覆盖前者 `display:grid`，摘要条布局失稳。
4. Overview 模式切换排在精简/完整之后；精简/完整以 `margin-left:auto` 挤在 meta 行，未进入稳定工具栏文档流。

## 2. 真实 DOM 结构（修复后）

```
.journey-overview-pane
  ├─ .journey-overview-mode-tabs          (曲线总览｜问题簇｜章节诊断)
  ├─ .journey-marker-toolbar              (说明 + 精简/完整)
  ├─ [data-reader-journey-export-root]
  │    ├─ .journey-export-title / .journey-export-meta
  │    └─ .journey-overview-curve
  │         ├─ summary strip
  │         ├─ phase band
  │         ├─ .journey-metric-switcher
  │         ├─ .journey-curve-legend
  │         └─ .journey-curve-section → SVG
  └─ .journey-rhythm-strip
```

## 3. CSS 冲突

- 破除 metric 与 chart 共盒 `overflow:hidden`。
- summary 恢复 `display:grid`（保留 `journey-metric-strip` 类名别名，避免旧测试语义漂移）。
- 去掉 marker-toggle 的 `margin-left:auto` 绝对化倾向；模式栏改为三列 grid。

## 4. 新布局顺序

见第 2 节；任何一层不得 `position:absolute` 覆盖下一层（情绪下拉菜单除外）。

## 5. 响应式规则

- Summary：`repeat(4, minmax(0,1fr))` → `≤1440` 两列 → `≤1024` 单列。
- Metric：`display:flex; flex-wrap:wrap; gap`；按钮 `white-space:nowrap`。
- Chart：`min-height: 260px`；与上方工具栏保留间距；父级 `min-width:0`。

## 6. PNG 无反应根因

1. `handleExport` 无 UI 状态；失败时 Promise reject 被 `void` 吞掉，无 loading/成功/失败提示。
2. `workspaceRef` 为空时静默 return。
3. `foreignObject`→`Image` 在 Chromium 常失败，且无用户可见错误。
4. `revokeObjectURL` 过早；缺少 export root 语义属性与渲染就绪校验。

## 7. 导出状态机

`idle → exporting → succeeded|failed → idle`（成功/失败提示 ≥2.5s 后清除）。  
导出中按钮文案「导出中…」且 `disabled`。

## 8. root 选择

稳定属性：`data-reader-journey-export-root="true"`（兼 `data-testid="journey-export-root"`）。  
只导出标题、版本 meta、摘要、Phase、曲线（含 H/P/R）、图例相关内容；不导出正文/Scene 详情/导航/分隔条。

## 9. 下载流程

校验 root → 临时 `journey-exporting` 解除裁剪 → `exportJourneyPng`（foreignObject，失败则同函数内 SVG+页眉回退）→ `toBlob` → `<a download>` click → 延迟 revoke。

## 10. 状态恢复

仅用 `exportForceCurve` 临时显示 curve，不改 URL `overview`；finally 清除 force，Scene/metric/split/详情 tab 均未改写。

## 11. 失败反馈

用户文案：未找到可导出的旅程图 / 尚未完成渲染 / 图像生成失败 / 未能触发下载 / 未知错误。  
开发环境 `console.error` 保留内部 error。

## 12. E2E

`e2e/phase_1cc251_blocking_ui_fix.spec.ts`：遮挡（1920/1280）、PNG 下载与恢复、失败反馈、独立结果路由。

## 13. Freeze 结果

- 生产白名单：`ReaderJourneyWorkspace.tsx` / `readerJourney.css` / `exportJourneyPng.ts`
- 未新增 v2-1（已在 v2 覆盖）
- 原 `core-freeze-manifest.json` / thaw v1 / v2 未改
- 改前/改后：`check_core_freeze` + `check_ui_presentation_thaw` = PASS
- FROZEN_CORE modified=0；FROZEN_CONTRACT modified=0
- 非白名单 REUSABLE_UI_LOGIC modified=0；未授权生产文件变化=0
- Pytest 271；Ruff PASS；Typecheck/ESLint/Vitest 192/Build/E2E 34 PASS
- SQLite integrity_check=ok；foreign_key_check=[]
- Run #55 / JourneyRun #2 保持 succeeded；真实模型请求/Token/费用/新 Run = 0
