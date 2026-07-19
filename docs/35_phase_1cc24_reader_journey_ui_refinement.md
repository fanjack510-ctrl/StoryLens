# docs/35｜Phase 1C-C.2.4 Reader Journey Progressive UI Refinement

**阶段：** 读者旅程总览、详情与视觉分阶段优化（展示层）  
**非目标：** 不改分析数据、公式、选择语义、Scroll Spy、导出数据语义；不调用真实模型。

## 1. 2.4A 布局

同步审阅右侧改为固定分区：

- Journey Overview：`minmax(min(320px, 48%), 48%)`，`overflow: hidden`（避免 `minmax(320px, 45%)` 在矮视口 min>max 导致叠层）
- Sync 右栏：总览约 `56%`，以保证 Phase 带与 ≥220px 曲线同时可见
- Scene Detail：`minmax(0, 1fr)`，独立 `overflow: auto`

## 2. 总览固定

点击 Scene 后 Phase 带与曲线仍可见；总览不产生独立竖向滚动。

## 3. 详情滚动

仅右下详情区滚动；左侧正文滚动保留。右侧 Split secondary 改为 `overflow: hidden`。

## 4. Phase 卡

固定高度 132px；默认仅显示编号、标题、Scene 范围、核心问题、阶段回报、平均牵引｜Core。完整说明进 `title` Tooltip。

## 5. 曲线

高度 248px；Y 轴 100/75/50/25/0；X 轴 S1—S14；指标切换中文文案。

## 6. Marker

章尾 / 阶段转折 / 关键钩子分层；Payoff 实心点；Risk 底部带；紧凑图例。当前 Scene 垂直定位线 + 放大描边。

## 7. 2.4B 五页签

`JourneySceneDetailPanel`：概览｜问题链｜回报与钩子｜写作技法｜证据。页签切换不改 URL Scene。

## 8. 问题生命周期

内部枚举经 `journeyUiLabels.lifecycleLabelZh` 中文化展示。

## 9. Hook 四格

已知 / 缺口 / 继续动力 / 下一场承接；历史缺字段兼容。

## 10. Evidence

证据页签集中列表；定位沿用既有 `onLocateEvidence` + 1.5s flash。

## 11. 2.4C 正文提示

当前 Scene 100%；同 Phase 85%；其他 Phase 70%。标题精简为 `Scene N｜等级中文｜Phase`；技术段落范围进悬停。

## 12. 章节摘要

顶部四卡：核心牵引 / 峰值 Scene / 最大薄弱区间 / 章尾钩子；完整诊断折叠。

## 13. 精简/完整视图

切换说明写入 banner/title；不丢 Scene、Phase、详情页签。

## 14. 响应式

≥1280 左右同步 + 上下总览/详情；900–1279 纵向分区；&lt;900 曲线/Phase 可横滑。

## 15. PNG

仍导出 `journey-export-root`（摘要卡 + Phase + 曲线 + 问题簇），不导出详情页签内容。  
导出前短暂解除 overview/export-root 裁剪，避免分区后 PNG 被裁切。

同步选择修补：Scene 选择与 Phase 高亮合并为单次 `selectPhase(..., sceneOrdinal)`，避免二次 `syncUrl` 用陈旧 scene 覆盖 URL。

## 16. UI 解冻白名单

`audits/mvp-functional-baseline-v1/ui-presentation-thaw-v1.json`（10 个生产展示文件）  
检查：`scripts/check_ui_presentation_thaw.py`  
原 `core-freeze-manifest.json` 未修改。

## 17. 核心冻结结果

- FROZEN_CORE modified=0  
- FROZEN_CONTRACT modified=0  
- 非白名单 REUSABLE_UI_LOGIC modified=0  
- 白名单展示文件允许变化（`check_core_freeze.py` 以 thawed 记账，不失败）
