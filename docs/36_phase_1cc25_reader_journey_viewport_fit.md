# docs/36｜Phase 1C-C.2.5 Reader Journey Viewport Fit Optimization

**阶段：** 读者旅程视口适配与信息分层优化（展示层）  
**非目标：** 不改分析数据、公式、选择语义、Scroll Spy、导出数据语义；不调用真实模型。

## 1. 原显示不全根因

固定 Overview 同时纵向堆积：四卡摘要、Phase 小作文、问题簇（含 absolute 浮层）、曲线、图例。  
在 1080P sync 右栏高度不足时，曲线被裁切/遮挡，浮层被 overflow 裁切。

## 2. Overview 三级视图

互斥入口：`曲线总览`｜`问题簇`｜`章节诊断`  
URL 展示参数：`overview=curve|questions|diagnosis`（默认 curve）  
由展示层 `overviewMode.ts` + `useSearchParams` 读写，**不修改** `useJourneySelection`。

## 3. Phase 结构带

曲线总览中 Phase 高度约 80px：编号、短标题、Scene 范围、平均牵引、当前状态。  
点击后紧凑 Popover 显示核心问题 / 阶段回报 / 继续动力 / 主要风险。

## 4. 曲线最小高度

曲线主体 `min-height: 260px`；Y 轴 0/25/50/75/100；X 轴 S1—S14；当前 Scene 定位线保留。

## 5. 问题簇展示

独立 Overview 视图；文档流展开成员链；取消覆盖曲线的 absolute 大浮层；视图内可滚动。

## 6. 章节诊断展示

独立 Overview 视图：四项摘要 + 节奏/回报/Hook/风险 + 完整诊断；内部滚动。

## 7. 上下拖动分隔线

`JourneyResizableSplit`：Overview / Detail 可拖；默认约 52%；最小 Overview 360px、Detail 260px；  
方向键微调；Home/End；双击或「重置旅程布局」恢复默认。

## 8. localStorage

Key：`storylens.readerJourney.overviewHeight.v1`  
存 ratio、viewportHeight、updatedAt；视口变化过大时回退高度默认值。

## 9. 响应式

内容高度 &lt;700px：总览｜Scene 详情切换。  
宽度：≥1440 左约 46%；1280–1439 左约 52%；900–1279 纵向分栏；&lt;900 正文｜旅程 Tab。

## 10. 紧凑指标条

曲线总览顶部四项一行：核心牵引｜峰值｜薄弱区间｜章尾钩子。

## 11. 图例与指标

默认图例：当前 Scene / Hook / Payoff / Risk；完整标记补充章尾/阶段钩子与问题图例。  
指标切换：阅读牵引、情绪（正负/唤醒下拉）、好奇、紧张、回报、钩子、风险。

## 12. PNG 导出

导出前临时强制 curve 视图并解除裁剪；导出后恢复用户 overview 与布局；不改 URL。

## 13. v2 展示白名单

`audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2.json`（≤12 生产文件）  
检查：`scripts/check_ui_presentation_thaw.py`（v1+v2 并集）  
原 `core-freeze-manifest.json` 未修改。

## 14. Freeze 结果

- FROZEN_CORE modified=0  
- FROZEN_CONTRACT modified=0  
- 非白名单 REUSABLE_UI_LOGIC modified=0  
- 真实请求 / Token / 费用 = 0；不新建 AnalysisRun / ReaderJourneyRun  
