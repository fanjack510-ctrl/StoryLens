# docs/43｜Phase 1C-C.2.6 Journey Analysis Focused View

**性质：** 展示层信息架构收敛。不改 Freeze Manifest、不写库、不调模型、不改 selection transaction / useJourneySelection。

## 1. 删除旧一级视图的原因

原 Reader Journey 顶部有三个一级入口：曲线总览｜问题簇｜章节诊断。

实际使用中：

- 曲线总览承担主要分析；
- 问题簇已在 Scene「问题链」与 Phase「问题与回报」可达；
- 章节诊断已在四项摘要与 Inspector 风险可达；
- 三个等宽 Tab 增加认知负担与页面高度。

## 2. 新信息架构

唯一页面「旅程分析」自上而下：

1. 标题「旅程分析」+ 章节信息
2. 右侧工具：精简标记｜完整标记｜导出PNG｜分析信息
3. 四项章节摘要
4. Phase 结构带
5. 指标选择器 + 图例
6. 阅读旅程曲线（主视觉，min-height 280px）
7. Scene 节奏带
8. 可拖分隔线
9. Context Inspector

## 3. 旅程分析命名

「旅程分析」仅为产品 UI 名称。合同中的 `visualization` 版本名、公式版本与数据语义不变。

## 4. 旧 URL 兼容

`overview=curve|questions|diagnosis` 均可打开同一旅程分析视图。

- `parseOverviewMode` 一律解析为内部规范值 `curve`
- 遇到 legacy `questions|diagnosis` 时 `replace` 规范化为 `overview=curve`
- 不丢 `scene` / `paragraph` / `inspector` / `metric`
- 不新增 ReaderJourneyRun

## 5. 问题簇数据保留位置

- Scene Inspector → 问题链
- Phase Inspector → 问题与回报
- question / hook / payoff inspector 仍可打开
- 导出摘要语义保留
- `JourneyQuestionsOverview` 组件保留为未挂载 helper（非一级入口）

## 6. 章节诊断数据保留位置

- 四项摘要：核心牵引 / 峰值 / 薄弱区间 / 章尾钩子
- Phase 节奏风险页签
- Scene 概览「核心风险」
- Context Inspector
- PNG/Markdown 既有诊断摘要

## 7. 指标选择器

取消「阅读牵引｜好奇｜紧张｜更多指标」平铺，改为：

`当前指标：阅读牵引 ▼`

菜单含全部既有 metric；底层 URL `metric=` 语义不变。

## 8. 摘要主次

桌面端权重：`2fr 1fr 1fr 2fr`（核心牵引、章尾钩子更宽）。

- ≤1280px：2×2
- ≤900px：单列

## 9. 曲线权重

释放 Tab + 说明条高度，曲线 `min-height: 280px`，成为 Overview 主视觉。不改曲线数据与点击语义。

## 10. PNG 变化

- 产品标题改为「旅程分析」
- 文件名：`StoryLens_<章>_旅程分析_v1.1.png`
- 不导出旧一级 Tab、Inspector、分隔线、正文区
- 版本与数据语义不变

## 11. v2-4 Thaw

`audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-4.json`

purpose: `single-journey-analysis-view`

白名单（8）：

1. ReaderJourneyWorkspace.tsx
2. ReaderJourneySyncWorkspace.tsx
3. JourneyOverviewModes.tsx
4. overviewMode.ts
5. readerJourney.css
6. syncWorkspace.css
7. exportJourneyPng.ts
8. journeyUiLabels.ts

未修改旧 Thaw / core-freeze-manifest。

## 12. Freeze

`check_core_freeze` / `check_ui_presentation_thaw` 需识别 v2-4（脚本仅追加 DEFAULT_THAW_V2_4）。

## 13. E2E

`apps/desktop/e2e/phase_1cc26_journey_analysis_focused_view.spec.ts`

覆盖 Books / 独立路由、旧 overview 兼容、指标、Scene 稳定、PNG。
