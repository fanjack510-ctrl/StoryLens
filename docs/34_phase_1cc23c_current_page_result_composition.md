# docs/34｜Phase 1C-C.2.3C Current-Page Result Composition

**阶段：** 章节当前页直接组合展示现有分析结果  
**非目标：** 不自动创建 Reader Journey；不修改分析内核；不复制 Scene/Evidence/Journey 逻辑；不删除旧结果路由。

## 1. 成功自动切换

AnalysisRun 从运行中变为 `succeeded` 后：

1. 停止进度轮询（沿用既有终态逻辑）；
2. 保留 `analysisRun`；
3. 将 `view` 设为 `result`（用户显式 `view=reading` 时不抢占）；
4. 当前 `/books/{bookId}` 页加载内嵌结果；
5. 不整页跳转到 `/analysis-runs/{id}/results`；
6. 不重新创建 Run；不自动启动 Reader Journey；不产生云端模型请求。

短暂状态文案：`分析完成，正在加载结果`。

## 2. 内嵌结果

组合层组件（UI only）：

| 组件 | 职责 |
|------|------|
| `EmbeddedAnalysisResultShell` | 结果数据预检、加载/错误、Error Boundary、壳层 class |
| `AnalysisResultRouteAdapter` | 向冻结的 `AnalysisResultsPage` 注入 `:runId`（`UNSAFE_RouteContext`） |
| `ChapterResultLoadingState` / `ChapterResultErrorState` | 加载与错误隔离 UI |

数据仍走现有 `analysisApi.results` / Scene paragraphs / Reader Journey 查询；与独立结果路由同一套 API。

## 3. Scene Analysis 复用

不复制 Scene 列表、正文映射、Evidence 定位。  
通过 Route Context 适配复用冻结的 `AnalysisResultsPage` 主体（Scene 列表｜正文｜Scene 详情）。

## 4. Reader Journey 复用

- 已有 succeeded + visualization：结果顶栏显示「读者旅程」，进入现有 `ReaderJourneySyncWorkspace`（经冻结结果页）；
- 无 Journey：仅分析视图 + 原有「生成读者旅程分析」入口（不自动点击）；
- partial/failed：沿用原有恢复入口，无第二套恢复逻辑。

零费用存在性查询沿用 Phase 1C-C.2.3B。

## 5. URL 状态

| 参数 | 含义 |
|------|------|
| `chapter` | 当前章节 |
| `analysisRun` | 当前 AnalysisRun |
| `view` | `reading` \| `progress` \| `result` |
| `resultTab` | 可选别名，归一为 `tab` |
| `tab` / `mode` / `scene` / `paragraph` / `metric` / `cluster` | 既有 JourneySelection / 结果 URL 语义 |

示例：

`/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=14`

不写入正文、Profile、错误堆栈或凭据。

## 6. 正文阅读切换

顶部「正文阅读」→ `view=reading`，保留 `analysisRun`，轻量提示「本章分析已完成」，可返回 `view=result`。  
成功后不长期展示大型进度面板；「更多 → 分析信息」可看完成时间 / Scene 数 / 费用摘要。

## 7. 旧路由兼容

`/analysis-runs/{run_id}/results` 继续由 `AnalysisResultsShellPage` 承载，不重定向到 `/books`。  
两种入口读取同一结果数据与同一冻结结果组件行为。

## 8. 错误隔离

内嵌结果加载失败：

- 不影响章节正文数据；
- 文案「分析结果暂时无法加载」；
- 提供重试 / 返回正文 / 打开独立结果页；
- 局部 Error Boundary 继续生效；不向用户展示内部堆栈。

## 9. Freeze 结果

`scripts/check_core_freeze.py`：

- FROZEN_CORE modified=0  
- FROZEN_CONTRACT modified=0  
- REUSABLE_UI_LOGIC modified=0  

策略：只新增 UI 组合层并扩展可改的 `BookRoutePage`；不修改 baseline manifest；不改 `AnalysisResultsPage` / SyncWorkspace / `useJourneySelection` 等冻结哈希。

适配说明：React Router 禁止嵌套 `MemoryRouter`，因此用 `UNSAFE_RouteContext` 注入 `runId`，`useSearchParams` 仍读写父级 `/books` search（含 journey 选择键）。

## 10. 后续自动 Reader Journey 边界

本阶段明确 **不** 自动创建 / 启动 Reader Journey。  
后续若做自动串联，须单独阶段、单独 Freeze 审阅，且不得复制 SyncWorkspace 或突破预算确认流程。
