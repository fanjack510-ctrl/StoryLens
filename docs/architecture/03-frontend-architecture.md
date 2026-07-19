# 03 — Frontend Architecture

## 技术栈

| 层 | 技术 | 版本（package.json） |
|----|------|----------------------|
| UI | React | ^19.0.0 |
| Router | react-router-dom | ^7.1.5（`createBrowserRouter`） |
| Server state | @tanstack/react-query | ^5.66.0 |
| Client state | zustand | ^5.0.3 |
| UI 组件 | 自研（无 MUI/Ant） | `components/common/States.tsx` 等 |
| 样式 | 纯 CSS | `styles/global.css` + 功能 CSS |
| 构建 | Vite | ^6.1.0 |
| 桌面壳 | Tauri | 2.x（`@tauri-apps/api` 已装但前端未深度调用） |
| 测试 | Vitest + Playwright + Testing Library | — |

**API Base：** `VITE_API_BASE_URL` 或默认 `http://127.0.0.1:8000`

## 目录结构（`apps/desktop/src`）

```
src/
├── app/           # App.tsx, router.tsx, queryClient.ts
├── pages/         # 路由页
├── components/    # layout / analysis / readerJourney / settings / ...
├── hooks/         # useCurrentPageAnalysisProgress, useJourneySelection
├── services/      # apiClient + books/analysis/providers/settings APIs
├── stores/        # uiStore, developerModeStore
├── types/         # 领域类型
└── styles/        # global.css
```

### pages

| 文件 | 用途 |
|------|------|
| `LibraryPage.tsx` | 我的书库 |
| `BookRoutePage.tsx` | 书籍主壳（阅读 / 进度 / 结果） |
| `BookWorkspacePage.tsx` | 正文三栏阅读工作区 |
| `TasksPage.tsx` | 任务中心（开发者模式） |
| `SettingsPage.tsx` | 设置 |
| `ProvidersPage.tsx` | 模型与 API（开发者模式） |
| `AnalysisResultsPage.tsx` / `AnalysisResultsShellPage.tsx` | 独立结果页 |
| `CasesPage.tsx` | 案例库占位（开发者模式） |
| `WorkspaceLandingPage.tsx` | 旧工作台入口（开发者模式） |

### components（重点）

- `layout/` — AppShell、工具栏、阅读设置、结果视图切换
- `analysis/` — StartAnalysisDialog、BoundaryReviewPanel
- `chapterAnalysis/` — 进度、失败、预算恢复、统一恢复卡、旅程恢复卡
- `chapterResult/` — 嵌入式结果壳
- `readerJourney/` — 旅程图表、同步工作区、指标选择、导出 PNG（约 40 文件）
- `settings/` — 通用 / AI 服务 / 预算隐私 / 高级
- `onboarding/` — Qwen 首次启动横幅

### stores

- `uiStore` — 主题、字号、行距、内容宽度、段落 ID 显示
- `developerModeStore` — 开发者模式（localStorage）

## 路由表

| Path | 页面 | 普通导航 |
|------|------|----------|
| `/` → `/library` | Home redirect | — |
| `/library` | LibraryPage | ✅ 我的书库 |
| `/books/:bookId` | BookRoutePage | 经书库进入 |
| `/settings` | SettingsPage | ✅ 设置 |
| `/analysis-runs/:runId/results` | AnalysisResultsShellPage | 直链 |
| `/tasks` | TasksPage | 开发者模式 |
| `/providers` | ProvidersPage | 开发者模式 |
| `/cases` | CasesPage | 开发者模式 |
| `/workspace` | WorkspaceLandingPage | 开发者模式 |

`BookRoutePage` 查询参数：`chapter`, `analysisRun`, `view=reading|progress|result`, `tab`, `mode`, `scene`, `paragraph`, `metric`, `cluster`, `overview`

---

## 功能详解

### 1. 我的书库

| 项 | 说明 |
|----|------|
| 入口 | `/library` |
| 核心组件 | `LibraryPage`, `QwenFirstLaunchBanner` |
| 数据来源 | React Query `["books"]` |
| API | `GET /api/v1/books`；导入 `POST .../chapter-detection/preview` + `POST .../books/import` |
| 阅读状态 | **无**跨会话书签（无 last-chapter 持久化） |
| 备注 | 文件类型筛选 / 排序 UI 未接线 |

### 2. 正文阅读

| 项 | 说明 |
|----|------|
| 入口 | `/books/:bookId?view=reading&chapter=` |
| 核心组件 | `BookRoutePage` + `BookWorkspacePage` + `ReadingSettingsPopover` |
| 数据来源 | book / chapters / paragraphs（分页） |
| API | `GET /books/{id}`, `/chapters`, `/chapters/{id}/paragraphs`；重解析相关 POST |
| 阅读偏好 | zustand + 可选同步 `PUT /settings/desktop` |
| 备注 | URL `chapter` 与嵌入阅读器本地 state 可能不同步 |

### 3. Scene 分析

| 项 | 说明 |
|----|------|
| 入口 | 书内「开始分析」→ `view=progress` / `view=result`；或 `/analysis-runs/:runId/results` |
| 核心组件 | `StartAnalysisDialog`, `BoundaryReviewPanel`, `ChapterAnalysisProgressPanel`, `EmbeddedAnalysisResultShell` |
| 数据来源 | `analysisApi` + `useCurrentPageAnalysisProgress`（约 2s 轮询） |
| API | preflight、create run、boundary review、results、resume、recover、export |

### 4. 阅读旅程 Journey

| 项 | 说明 |
|----|------|
| 入口 | `view=result&tab=reader-journey` |
| 核心组件 | `ReaderJourneySyncWorkspace`, `CanonicalJourneyChart`, `MetricSelectorPanel`, Inspector |
| 数据来源 | journey GET + progress；选择状态 URL + localStorage |
| API | reader-journey create/preflight/get/resume/export；PNG 客户端生成 |

### 5. 任务中心

| 项 | 说明 |
|----|------|
| 入口 | `/tasks`（开发者模式） |
| 核心组件 | `TasksPage` |
| 数据来源 | `analysisApi.runs()` 约 5s 轮询 |
| API | runs 列表、retry、resume、offline replay、recovery、invocations |
| 备注 | 外链 `?run_id=` 未消费 |

### 6. 设置中心

| 项 | 说明 |
|----|------|
| 入口 | `/settings?tab=general|ai|budget|advanced` |
| 核心组件 | Settings*Tab 四个页签 |
| API | desktop settings、cloud、cloud-budget、usage |

### 7. API 配置

| 项 | 说明 |
|----|------|
| 普通入口 | `/settings?tab=ai`（Qwen 向导） |
| 开发入口 | `/providers` |
| 核心组件 | `SettingsAiServiceTab`, `AliyunForm`, ProvidersPage |
| API | model-providers CRUD/connect/test；credentials DELETE；local-model start/stop |
