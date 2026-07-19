# docs/33｜Phase 1C-C.2.3B Current-Page Analysis Progress

**阶段：** 章节当前页分析进度组合  
**非目标：** 不实现单页面完整结果工作台；不自动启动 Reader Journey；不新建工作流表。

## 1. 当前页分析流程

1. 章节页点击「开始分析」→ 复用现有 `StartAnalysisDialog`（Preflight / Consent / create）。
2. `createAnalysisRun` 成功后 **不再** `navigate("/tasks")`。
3. 通过 `onCreated` 将 `analysisRun`（及 `chapter`）写入当前 `/books/{bookId}` URL（`replace`）。
4. 右侧「章节分析」进度面板轮询现有 `GET /api/v1/analysis-runs/{id}`。
5. 成功后主操作进入现有 `/analysis-runs/{id}/results`。

## 2. URL 状态

| 参数 | 含义 |
|------|------|
| `chapter` | 当前/任务所属章节 ID |
| `analysisRun` | 现有 AnalysisRun ID |

示例：`/books/1?chapter=2&analysisRun=55`

不写入正文、凭据、费用明细或错误堆栈。刷新时读取 `analysisRun` 恢复轮询，不重新创建任务。

## 3. 进度轮询

- Hook：`useCurrentPageAnalysisProgress`
- 接口：现有 `analysisApi.run(id)`（无第二套进度 API）
- 非终态：约 2s；页面隐藏：约 12s；可见时立即 refetch
- `succeeded` / `failed` / `cancelled` 停止
- 网络连续失败：显示「正在重新连接」，保留上次成功快照，不误标 failed
- 卸载由 React Query 清理；不调用 Reader Journey 轮询接口

## 4. 刷新恢复

带 `analysisRun` 打开章节页 → 拉取同一 Run → 展示对应 UI 状态 → 不 create、不扣费。

## 5. 边界审阅

后端状态 `awaiting_boundary_review` 映射为 UI `boundary_review_required`。  
进度面板主按钮打开现有 `BoundaryReviewPanel`（壳层模态宿主），不跳任务中心，不自动接受边界。

## 6. 成功状态

- 文案：分析完成
- 摘要：Scene 数量 / 覆盖 / 是否已有 Reader Journey（成功后一次性查询，不自动创建）
- 主操作：查看分析结果（或「查看正文与读者旅程」）→ 现有结果路由
- 次级：继续阅读正文（收起面板）

## 7. 失败和恢复

`failed` / `partial`（含 `scene_analysis_partial`、`boundary_candidates_partial`、预算阻塞）显示失败卡。  
「恢复分析」调用现有 `resumeSceneAnalysis` 或 `continueFromCheckpoints`，保持同一 `analysisRun`。  
技术详情默认折叠。

## 8. 任务中心兼容

- `/tasks` 路由与功能不变
- 创建后不再自动跳转
- 章节页「更多 → 查看任务记录」可进入任务中心
- 开发与诊断导航仍可访问任务中心

## 9. Freeze 结果

`scripts/check_core_freeze.py`：

- FROZEN_CORE modified=0  
- FROZEN_CONTRACT modified=0  
- REUSABLE_UI_LOGIC modified=0  

策略：新 UI 组合层 + `BookRoutePage` composition；不改 baseline manifest；不改 `StartAnalysisDialog` / `TasksPage` 哈希。

## 10. 后续结果页嵌入边界

本阶段之后若做单页结果嵌入：

- 仍须遵守 Core Freeze  
- 不得复制 SyncWorkspace / useJourneySelection  
- 不得自动串联 Reader Journey  
- 可继续以 `analysisRun` URL 为锚点挂载现有结果壳层  

## 用户启动与验证步骤

1. 我的书库 → 打开书籍章节页  
2. 开始分析 → 完成 Preflight/确认 → 创建任务  
3. 确认 URL 出现 `analysisRun=` 且未进入 `/tasks`  
4. 右侧查看进度 → 成功后「查看分析结果」  
5. 需要技术排障时：更多 → 查看任务记录 / 开发与诊断  
