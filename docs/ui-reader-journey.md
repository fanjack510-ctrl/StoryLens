# Reader Journey UI（阶段 3A.2）

## 原布局问题

主内容被压到左侧约 200–240px、右侧大面积空白的根因：

1. 工作台结果页把旅程挂在 `section.workspace.results-page-journey-sync` 上。
2. `.workspace` 默认是三栏网格（`260px | 1fr | 390px`）。
3. 阶段 3A 阅读区规则 `.book-shell-simplified .workspace:not(:has(.artifact))` 用更高特异性把任意无 artifact 的 `.workspace` 改成 `240px | 1fr`。
4. 旅程同步页只有一个子节点，于是整页旅程落进第一列（约 240px），第二列空白。
5. `@media (max-width: 1280px)` 里的 `.workspace { 220px | 1fr | 330px }` 也会在独立结果壳中覆盖 `.results-page-journey-sync { 1fr }`。

修复：排除 `results-page-journey-sync`，并提高旅程页 `grid-template-columns: minmax(0, 1fr)` 优先级；主栏继续依赖 `min-width: 0` 与图表 ResizeObserver，不写死 `width: 1200px`。

## 新页面结构

```text
ReaderJourneySyncWorkspace
├─ 二级视图（正文对照 / 旅程视图 / 仅看正文）
├─ 生成与任务（默认折叠）
└─ ReaderJourneyWorkspace
   ├─ JourneyHeader（阅读旅程 + 章节 + 场景/阶段摘要）
   ├─ JourneyMetricSelector（主指标分段 + 更多指标）
   ├─ PhaseSummaryCards
   ├─ CanonicalJourneyChart + ChartLegend
   └─ JourneyDetailInspector（展开/收起，不留空白列）
```

顶层工作台入口保持：`正文阅读` · `场景分析` · `阅读旅程` · `更多`。内部模式切换改为二级文案，避免与顶栏重复。

## 响应式策略

| 宽度 | 行为 |
|------|------|
| ≥1440 | 主曲线 + 右侧详情（约 300–360px）；详情收起后曲线吃满释放宽度 |
| 1180–1439 | mid：详情可底栏停靠；曲线仍占主体 |
| &lt;1180 / 1024 | narrow：详情为覆盖/页签；阶段卡横向滚动；禁止页面水平滚动；图表有效宽度 ≥560px |

## 数据与业务边界

- 不改 Reader Journey 算法、评分、Phase/Scene/Node 排序、schema、API、query key、mutation、route、artifact/ID。
- 展示层映射（`formatJourneyPhaseLabel` / `formatJourneyMetricLabel` 等）只改中文文案。
- 无 summary 时只用固定阶段说明，不伪造剧情结论。
- Tooltip / 导出仍使用真实节点数据。

## UI Audit 覆盖

`06_reader_journey.spec.ts` 覆盖默认/加载/空/失败/成功、指标、阶段/节点选择、Tooltip、详情展开收起、1024、深色等截图；断言拦截窄图表与脏可见文本（undefined / NaN / Phase / Scene # / Task Control 等）。
