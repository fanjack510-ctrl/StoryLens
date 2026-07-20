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

布局模式按**浏览器 viewport**判定（非导航栏扣除后的 host 宽度），避免 1440px 视口被误判为 mid 底栏。

| 宽度 | 行为 |
|------|------|
| ≥1440 | 主曲线 + 右侧 Inspector（约 320–360px）；仅一个「收起」；收起后曲线吃满释放宽度 |
| 1180–1439 | mid：较窄右侧或底栏停靠；依据真实 viewport |
| &lt;1180 / 1024 | narrow：覆盖抽屉/页签；阶段卡两列；禁止页面水平滚动；图表有效宽度 ≥560px |

## 状态真实性（3A.2.1）

- Empty：artifact 成功但无可视化数据 →「暂时没有可显示的阅读旅程」
- Failed：旅程生成失败 StateView + 重新生成 / 查看任务详情（不用分析暂停冒充）
- Paused：尚未生成旅程时的恢复卡，截图独立命名 `analysis_paused`
- 深色：必须经产品 `.theme-toggle-btn` → `.app[data-theme=dark]`，禁止只写 manifest
- 节点与场景选择在当前产品中为同一 Inspector 交互 → `same_interaction`，不生成重复假截图

## 数据与业务边界

- 不改 Reader Journey 算法、评分、Phase/Scene/Node 排序、schema、API、query key、mutation、route、artifact/ID。
- 展示层映射（`formatJourneyPhaseLabel` / `formatJourneyMetricLabel` 等）只改中文文案。
- 无 summary 时只用固定阶段说明，不伪造剧情结论。
- Tooltip / 导出仍使用真实节点数据。

## UI Audit 覆盖

`06_reader_journey.spec.ts` 覆盖默认/加载/空/失败/成功、指标、阶段/节点选择、Tooltip、详情展开收起、1024、深色等截图；断言拦截窄图表与脏可见文本（undefined / NaN / Phase / Scene # / Task Control 等）。
