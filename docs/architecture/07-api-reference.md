# 07 — API Reference

Base URL: `http://127.0.0.1:8000`  
统一错误字段常见形态：`error_code`, `message`, `details`（含预算相关扩展）。

下列「调用页面」指桌面端主要消费者。

---

## Health / System

### `GET /health`

- **用途：** 进程与 DB / 默认 provider 探活  
- **参数：** 无  
- **返回：** status / db / provider 摘要  
- **调用页面：** `AppShell` 轮询  

### `GET /api/v1/system/capabilities`

- **用途：** 能力 schema 版本  
- **调用页面：** 诊断 / 开发  

### `GET /api/v1/system/diagnostics` / `GET /api/v1/dashboard/summary`

- **用途：** 系统诊断 / 仪表盘计数  
- **调用页面：** Settings Advanced / Providers  

---

## Books

### `POST /api/v1/books/import`

- **用途：** 导入 TXT/DOCX/EPUB  
- **参数：** multipart file  
- **返回：** book_id, chapter_count, paragraph_count, warnings  
- **调用页面：** LibraryPage  

### `POST /api/v1/books/chapter-detection/preview`

- **用途：** 导入前章节预览（不落库）  
- **调用页面：** LibraryPage  

### `GET /api/v1/books` / `GET /api/v1/books/{book_id}`

- **用途：** 列表 / 详情  
- **调用页面：** LibraryPage, BookRoutePage  

### `GET /api/v1/books/{book_id}/import-diagnostics`

- **用途：** 导入诊断 JSON  
- **调用页面：** BookRoutePage / ReparseDialog  

### `POST /api/v1/books/{book_id}/reparse-preview` | `reparse` | `reparse-with-file-preview` | `reparse-with-file`

- **用途：** 重解析预览与确认（可换文件）  
- **调用页面：** ReparseDialog  

### `GET /api/v1/books/{book_id}/chapters`

- **用途：** 章节列表  
- **调用页面：** BookRoutePage / BookWorkspacePage  

### `GET /api/v1/chapters/{chapter_id}/paragraphs`

- **用途：** 段落列表（支持 offset/limit/paragraph_id）  
- **调用页面：** 阅读器 / 旅程文本窗格  

---

## Analysis Runs

### `GET /api/v1/analysis-runs`

- **用途：** 运行列表（可过滤）  
- **调用页面：** TasksPage, discoverActiveChapterRun  

### `POST /api/v1/analysis-runs/preflight`

- **用途：** 创建前预算/资格检查  
- **调用页面：** StartAnalysisDialog  

### `POST /api/v1/analysis-runs/full-pipeline-preflight`

- **用途：** 端到端预算建议  
- **调用页面：** StartAnalysisDialog / Recovery  

### `POST /api/v1/chapters/{chapter_id}/analysis-runs`

- **用途：** 创建分析任务（202 + 后台）  
- **参数：** provider/model/consent/client_request_id/预算授权等  
- **返回：** AnalysisRun  
- **调用页面：** StartAnalysisDialog  

### `GET /api/v1/analysis-runs/{run_id}`

- **用途：** 状态/进度/错误  
- **调用页面：** ProgressPanel（轮询）  

### `POST /api/v1/analysis-runs/{run_id}/retry`

- **用途：** 失败重试  
- **调用页面：** TasksPage / FailureCard  

### `GET /api/v1/analysis-runs/{run_id}/recovery-plan`

- **用途：** 统一恢复计划  
- **调用页面：** UnifiedAnalysisRecoveryCard  

### `POST /api/v1/analysis-runs/{run_id}/recover`

- **用途：** 统一恢复执行（boundary/scene/journey）  
- **调用页面：** UnifiedAnalysisRecoveryCard  

### `POST .../continue-from-checkpoints` / recovery-preflight / recover/preflight

- **用途：** 边界 checkpoint 续跑与预算  
- **调用页面：** Tasks / Recovery  

### `GET|POST .../resume-scene-analysis/preflight` / `POST .../resume-scene-analysis`

- **用途：** 场景分析续跑  
- **调用页面：** Progress / Tasks  

### `POST .../replay-scene-analysis-offline`（及 alias）

- **用途：** 无云端重放已存 invocations  
- **调用页面：** Tasks（开发）  

### `GET .../results` / `GET .../results/export`

- **用途：** 结果包 / json|markdown 导出  
- **调用页面：** AnalysisResultsPage  

### `GET .../scenes` / `GET .../model-invocations`

- **用途：** 场景列表 / 调用审计  
- **调用页面：** Results / Tasks  

### Scenes

| 接口 | 用途 | 调用页面 |
|------|------|----------|
| `GET /api/v1/chapters/{id}/scenes` | 章最新场景 | 阅读侧栏 |
| `GET /api/v1/scenes/{id}` | 场景元数据 | Results |
| `GET /api/v1/scenes/{id}/analysis` | 单场景分析 | Results |
| `GET /api/v1/scenes/{id}/analysis-artifacts` | 原始工件 | Results |
| `GET /api/v1/scenes/{id}/paragraphs` | 场景段落 | Results |
| `GET /api/v1/artifacts/{id}/evidence` | 证据行 | Results |

---

## Boundary Review

| 接口 | 用途 | 调用页面 |
|------|------|----------|
| `GET /books/{b}/chapters/{c}/boundary-review` | 取审阅会话 | BoundaryReviewPanel |
| `POST /analysis-runs/{r}/boundary-review/start` | 启动审阅 | BoundaryReviewPanel |
| `PUT /boundary-reviews/{id}/decisions/{tid}` | 决策 | BoundaryReviewPanel |
| `POST .../manual-boundaries` | 手动画界 | BoundaryReviewPanel |
| `DELETE .../manual-boundaries/{tid}` | 删除手动 | BoundaryReviewPanel |
| `GET .../scene-preview` | 预览场景切分 | BoundaryReviewPanel |
| `GET .../scene-analysis-preflight` | 确认前预算 | BoundaryReviewPanel |
| `POST .../confirm` | 确认并开场景分析 | BoundaryReviewPanel |
| `POST .../cancel` | 取消 | BoundaryReviewPanel |

---

## Reader Journey

| 接口 | 用途 | 调用页面 |
|------|------|----------|
| `POST /analysis-runs/{r}/reader-journey/preflight` | 预算 | Journey cards / dialog |
| `POST /analysis-runs/{r}/reader-journey` | 创建（202） | Journey |
| `GET /analysis-runs/{r}/reader-journey` | 取结果 | Results / SyncWorkspace |
| `GET /reader-journey-runs/{id}/progress` | 进度 | ProgressCard |
| `POST .../resume` | 续跑 | ResumeCard |
| `POST .../scene-profiles/offline-replay` | 离线重放 | Tasks |
| `POST .../semantic-recalibrate` | 语义校准 | Dev / Results |
| `POST .../cancel` | 取消 | Tasks |
| `GET .../export` | JSON 导出 | Results |

---

## Settings / Providers / Local Model

| 接口 | 用途 | 调用页面 |
|------|------|----------|
| `GET/PUT /settings/desktop` | 桌面偏好 | Settings General |
| `GET/PUT /settings/cloud` | 云端总开关 | Settings AI / Budget |
| `GET/PUT /settings/cloud-budget` | 日预算 | Settings Budget |
| `GET /cloud-usage/summary` | 用量 | Settings Budget |
| `GET /cloud-pricing/status` | 定价表状态 | Settings / Providers |
| `GET /model-providers` | Provider 列表 | Settings AI / Providers |
| `GET /model-providers/{n}/health` | 健康 | Providers |
| `GET/PUT .../configuration` | 配置 | Settings / Providers |
| `POST .../connect\|disconnect\|enable\|disable` | 生命周期 | Providers / AI tab |
| `POST .../validate-configuration` | 校验 | Providers |
| `POST .../transport-diagnostic` | 传输探测 | Providers / Advanced |
| `POST .../test/preflight` + `.../test` | 连接测试 | Providers / AI |
| `DELETE .../credentials` | 删除 Key | Settings / Providers |
| `GET /model-routing/preview` | 路由预览 | Advanced |
| `POST /local-model/start\|stop` + `GET status` | 本地模型 | Providers（开发） |

---

## 方法统计（约）

- **GET：** 健康、列表、详情、进度、结果、设置、诊断为主  
- **POST：** 导入、创建任务、恢复、测试、旅程、确认审阅  
- **PUT：** 设置、Provider 配置、边界决策  
- **DELETE：** 手动边界、凭证  

完整路径清单见 `audits/v1.0-baseline/api-registry.md`。
