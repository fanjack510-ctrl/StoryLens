# UI Change Boundary (Phase 1C-C.2.2-Baseline)

本文件定义后续 UI 阶段（含暂缓的 Phase 1C-C.2.3）的修改边界。**本阶段未实现任何 UI 改造。**

## 正式保护规则

1. UI 阶段不得修改 `FROZEN_CORE`（见 `core-freeze-manifest.json`）。
2. 修改 `FROZEN_CONTRACT` 必须单独立项，并同步后端 Schema / 前端类型 / 测试。
3. `REUSABLE_UI_LOGIC` 只能通过外部 props、composition 和 CSS 复用；不得复制第二套行为实现。
4. 不复制第二套分析逻辑（boundary / scene analysis / journey pipeline）。
5. 不复制第二套选择状态（必须复用 `useJourneySelection`）。
6. 不复制第二套 Scene / Paragraph / Evidence 映射（必须复用 `StructuredChapterTextPane` 与现有 ID 语义）。
7. 不修改 Prompt 来适配 UI。
8. 不修改数据库 Schema / 迁移来适配布局。
9. 不修改业务错误码来简化前端展示。
10. 不删除旧路由；先做兼容入口（例如从书页深链到现有 results）。
11. 所有 UI 提交后必须执行 Core Freeze 检查（比对 `sha256`）。
12. Run #55 + JourneyRun #2 黄金样本必须保持一致（只读核验可重复）。

## 分类摘要

| 类别 | 数量 | 含义 |
|------|------|------|
| FROZEN_CORE | 60 | 禁止改 |
| FROZEN_CONTRACT | 15 | 可读，语义禁止静默变更 |
| REUSABLE_UI_LOGIC | 15 | 行为冻结，允许外壳/样式包装 |
| UI_SHELL_CHANGEABLE | 16 | 允许改导航、壳层、文案、布局 |

## UI_SHELL_CHANGEABLE（可安全修改）

- `apps/desktop/src/app/router.tsx` — 可增兼容路由，勿删旧 path
- `apps/desktop/src/app/App.tsx`
- `apps/desktop/src/components/layout/AppShell.tsx` — 导航/页脚
- `apps/desktop/src/pages/HomePage.tsx`
- `apps/desktop/src/pages/LibraryPage.tsx` — 视觉与空状态可改；导入调用契约不可改
- `apps/desktop/src/pages/WorkspaceLandingPage.tsx`
- `apps/desktop/src/pages/CasesPage.tsx`
- `apps/desktop/src/pages/ProvidersPage.tsx` — 壳层可改；provider API 契约不可改
- `apps/desktop/src/pages/SettingsPage.tsx`
- `apps/desktop/src/pages/BookRoutePage.tsx`
- `apps/desktop/src/components/common/States.tsx`
- `apps/desktop/src/components/readerJourney/SceneStructureDrawer.tsx` — chrome 可改；testid 保留
- `apps/desktop/src/components/readerJourney/journeyVisualTokens.ts` — 颜色 token
- `apps/desktop/src/components/readerJourney/readerJourney.css`
- `apps/desktop/src/components/readerJourney/syncWorkspace.css`
- `apps/desktop/src/styles/global.css`

> 注意：`LibraryPage` / `ProvidersPage` 若改动到 API 调用语义，则越界进入 CONTRACT。壳层修改应限于布局与文案。

## REUSABLE_UI_LOGIC（复用，不重写）

见 manifest。重点：

- `ReaderJourneySyncWorkspace`
- `StructuredChapterTextPane`
- `useJourneySelection`
- `ReaderJourneyWorkspace` + `sceneDetailFields` + `safeRender`
- `JourneyDetailErrorBoundary`
- 导出：`exportJourneyPng` / `exportSceneCard*`
- 任务恢复：`TasksPage` 状态机
- 分析创建：`StartAnalysisDialog` / `BoundaryReviewPanel`

允许：改变外层布局包装、面板宽度默认值（若经 props）、视觉样式。  
禁止：改变 URL 参数语义、scroll spy 抑制窗口、evidence flash 时长语义、testid 契约。

## 未来单页面 UI：复用 vs 聚合层（只分析）

### 可直接复用

- 现有 `AnalysisRun` + `ReaderJourneyRun` 状态机与 API
- `ReaderJourneySyncWorkspace` 作为结果查看主面板
- `BookWorkspacePage` 章节正文加载与 evidence locate
- `TasksPage` 恢复卡片逻辑（可嵌入抽屉，不必新写）
- Preflight / consent / budget 闸门

### 可能需要的“聚合层”（未实现；本阶段禁止落地）

| 能力 | 是否需要新表 | 判断 |
|------|--------------|------|
| ChapterAnalysisWorkflow 新表 | **否（当前不必要）** | 可用 `AnalysisRun` + 关联 `ReaderJourneyRun` + BoundaryReviewSession 聚合 |
| 工作流状态 API | 可选只读聚合 endpoint | 属 CONTRACT 变更，需单独立项；非 UI-only |
| 浏览器触发下一阶段 | 部分需要 | 边界确认、云端同意、预算不足恢复仍需用户动作 |
| 后台连续执行 | 已支持部分 | 边界生成后停在 review；确认后可后台 scene analysis；journey 需用户显式启动 |
| 书页嵌入 SyncWorkspace | UI 即可 | 路由/composition 级；需有 succeeded journey + visualization |
| 旧 results 路由兼容 | UI | 保留 `/analysis-runs/:id/results`；单页作为额外入口 |

### 仍需用户手动确认的节点

1. 云端 `cloud_consent`
2. 边界审阅 confirm（assisted 模式强制）
3. 预算 blocked 后的 resume 同意
4. Reader Journey 创建（当前不自动连锁）
5. 离线重放 / 付费 resume 的同意勾选

### 会发生真实费用的节点

- 云端 boundary detection / adjudication
- 云端 scene analysis
- 云端 reader journey scene/chapter 调用  
Preflight、visualization、semantic recalibrate、offline replay = 0 Token。

### 哪些改动属于 UI vs 触碰内核

| 改动 | 归属 |
|------|------|
| 合并导航、减少页面跳转、嵌入 SyncWorkspace | UI |
| 保留旧路由深链 | UI |
| 新工作流表 / 自动串联 journey | 内核 + CONTRACT（禁止本阶段） |
| 改错误码 / Prompt / 公式 | 内核（禁止） |
| 新聚合 GET 返回组合状态 | CONTRACT（需立项） |

## 可安全删除的纯 UI 元素（候选，未执行）

- Home 仪表盘占位文案
- Cases 演示页入口（若产品确认无用）
- 重复的 Workspace Landing 与 Library 的双重入口文案

## 暂时不能删除的入口

- `/library` 导入
- `/books/:id` 阅读与开始分析 / 边界审阅
- `/tasks` 恢复与 resume
- `/analysis-runs/:id/results`（含 `tab=reader-journey` URL 恢复）
- `/providers` / `/settings` 云端预算与连接测试
