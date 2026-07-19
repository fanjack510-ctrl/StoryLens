# 02 — System Architecture

## 整体架构

```
用户
  ↓
Frontend React / Vite / Tauri (apps/desktop :1420)
  ↓  HTTP JSON
API Layer (/api/v1/*)
  ↓
FastAPI Backend (apps/api :8000)
  ↓
  ├─ SQLite (books, runs, scenes, journeys, budgets, invocations)
  ├─ Model Gateway → AI Provider (Aliyun Qwen BYOK / optional local)
  └─ Analysis Pipeline (BackgroundTasks)
        ├─ Boundary Detection
        ├─ Boundary Review (human)
        ├─ Scene Analysis
        └─ Reader Journey
```

## 模块职责

| 模块 | 路径 | 职责 | 输入 | 输出 |
|------|------|------|------|------|
| Desktop UI | `apps/desktop` | 书库、阅读、分析进度、旅程可视化、设置 | 用户操作 | HTTP 请求 |
| FastAPI App | `apps/api/app/main.py` | 路由注册、生命周期、健康检查 | HTTP | JSON |
| Books API | `api/v1/router.py` | 导入 / 重解析 / 章节段落 | 文件 / book_id | Book/Chapter/Paragraph |
| Analysis API | `api/v1/analysis.py` | 创建 run、结果、恢复相关 | chapter_id / run_id | AnalysisRun / Scenes |
| Recovery API | `api/v1/analysis_recovery.py` | 统一恢复计划与执行 | run_id | plan / recover |
| Boundary Review API | `api/v1/boundary_reviews.py` | 人工边界审阅 | review decisions | BoundaryRevision + scenes |
| Reader Journey API | `api/v1/reader_journey.py` | 旅程生成 / 进度 / 导出 | run_id | Journey result |
| Desktop/Settings API | `api/v1/desktop.py` | Provider、预算、桌面偏好、本地模型 | settings | config / usage |
| DB Layer | `app/db/` | SQLAlchemy models + SQLite migrations | ORM | 持久化 |
| Model Gateway | `app/model_gateway/` | 统一 Provider 协议 | ModelRequest | ModelResponse |
| Services | `app/services/` | 流水线编排、预算、校验、导出 | domain objects | artifacts / status |
| Prompts | `packages/prompts/` | 各任务 system/user/repair 模板 | task+version | prompt text |

## 数据流（单章闭环）

1. **Import：** 文件 → extractors → chapter detection → `books` / `chapters` / `paragraphs`
2. **Create run：** UI preflight → `analysis_runs`（queued）→ `BackgroundTasks.execute_scene_pipeline`
3. **Boundary：** 分批模型调用 → checkpoints → candidates →（云端）`awaiting_boundary_review`
4. **Review confirm：** decisions → `boundary_revisions` → `scenes` → scene analysis 后台任务
5. **Scene analysis：** 每场景 validated JSON → `analysis_artifacts` + `analysis_evidence`
6. **Reader Journey：** scene profiles → chapter synthesis → journey tables + 前端可视化
7. **Export：** 服务端 JSON/MD；客户端 PNG（旅程图）

## 关键设计约束

- 模型输出必须经 Pydantic 校验
- 文学结论必须引用真实段落 ID
- Provider 不写死在业务流水线；普通 UI 默认只暴露 Qwen
- 失败可重试、可定位、可单项恢复
- API Key 仅环境变量 / Keyring，禁止写入源码与日志

## 运行拓扑（本机）

| 进程 | 地址 | 说明 |
|------|------|------|
| Vite / Tauri WebView | `127.0.0.1:1420` | 桌面 UI |
| Uvicorn FastAPI | `127.0.0.1:8000` | 本地 API |
| 外部 | 阿里云 DashScope OpenAI-compatible | 用户自备 Key |
