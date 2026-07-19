# 04 — Backend Architecture

## FastAPI 结构

```
apps/api/app/
├── main.py                 # 应用入口、lifespan、路由挂载
├── api/v1/                 # HTTP routers
│   ├── router.py           # books / chapters / paragraphs
│   ├── analysis.py         # analysis runs / scenes / results
│   ├── analysis_recovery.py
│   ├── boundary_reviews.py
│   ├── reader_journey.py
│   └── desktop.py          # settings / providers / budget / local model
├── core/config.py          # STORYLENS_* settings
├── db/
│   ├── models.py           # 22 tables
│   └── session.py          # engine + inline migrations
├── domain/ingestion.py     # 章节检测规则
├── model_gateway/          # Provider 抽象与 OpenAI-compatible 实现
├── schemas/                # Pydantic I/O
├── services/               # 业务编排（约 50 模块）
└── workers/                # 占位（无独立 worker 进程）
```

**异步模型：** FastAPI `BackgroundTasks`（无 Celery/Redis）。

---

## 逐模块说明

### 1. 小说导入模块

| | |
|--|--|
| **入口** | `POST /api/v1/books/import`（`router.py` → `book_service`） |
| **输入** | TXT / DOCX / EPUB multipart |
| **处理** | `extractors` 抽文本 → `domain/ingestion` 章节候选打分 → 段落编号 → 写库 |
| **输出** | `books` / `chapters` / `paragraphs`；`import_diagnostics_json` |
| **相关** | preview / reparse / reparse-with-file；`reparse_audits` |

### 2. 分析运行模块

| | |
|--|--|
| **入口** | `POST /api/v1/chapters/{chapter_id}/analysis-runs` |
| **输入** | chapter_id、provider/model、consent、client_request_id、预算授权 |
| **处理** | 创建 `analysis_runs` → 预算预留 → `execute_scene_pipeline` 后台执行 |
| **输出** | 202 + run 状态；后续边界候选 / 审阅等待 / 场景分析 |

### 3. 边界检测模块

| | |
|--|--|
| **服务** | `scene_pipeline`, `transition_batch_planner`, `boundary_detection_checkpoints`, `scene_boundary_adjudicator` |
| **输入** | 章节段落窗口 / 批次 |
| **处理** | Prompt `scene_boundary`（云端默认 v3.5）→ 校验 → checkpoint →（可选）裁决 |
| **输出** | artifacts `scene_boundary`；checkpoints；进入人工审阅或自动建场景 |

### 4. 边界审阅模块

| | |
|--|--|
| **入口** | `boundary_reviews.py` + `boundary_review_service` |
| **输入** | 候选 transition 的 accept/reject/manual |
| **处理** | session + decisions → confirm → 不可变 `boundary_revisions` → 创建 `scenes` |
| **输出** | 确认后排队 `analyze_confirmed_review`（场景分析） |

### 5. Scene Analysis 模块

| | |
|--|--|
| **服务** | `boundary_review_service.analyze_confirmed_review` / pipeline 自动路径；`structured_output` |
| **输入** | 场景段落范围 |
| **处理** | Prompt `scene_analysis` → Pydantic `SceneAnalysisResult` → 证据段落校验 |
| **输出** | `analysis_artifacts` + `analysis_evidence`；可 partial / provider recovery |

### 6. Reader Journey 模块

| | |
|--|--|
| **入口** | `reader_journey.py` → `reader_journey_pipeline` |
| **输入** | 已完成场景分析结果 |
| **处理** | 分批 scene profiles → chapter synthesis → 统计/参与度/语义校准 |
| **输出** | `reader_journey_runs` + profiles/phases/summary；可 resume / offline replay |

### 7. 统一恢复模块

| | |
|--|--|
| **入口** | `GET .../recovery-plan`，`POST .../recover` |
| **服务** | `analysis_recovery_center` |
| **处理** | 汇总 blockers（预算、provider、checkpoint、旅程）→ 分发恢复动作 |
| **输出** | 继续边界 / 场景 / 旅程；支持 run-scoped 临时请求额度 |

### 8. Model Gateway 模块

| | |
|--|--|
| **路径** | `model_gateway/` + `services/model_invocation_broker.py` |
| **输入** | `ModelRequest`（冻结的 run provider/model） |
| **处理** | OpenAI-compatible HTTP；重试；策略门禁（禁止未授权 Flash/Max 回退） |
| **输出** | `ModelResponse` + `model_invocations` 审计行 |
| **凭证** | `services/credentials/`（keyring / fake for tests） |

### 9. 预算与设置模块

| | |
|--|--|
| **服务** | `cloud_budget`, `staged_budget`, `budget_reservation`, `run_scoped_budget_auth`, `cloud_pricing` |
| **表** | `cloud_budget_reservations`, `request_gate_decisions`, `application_settings`, `provider_configurations` |
| **API** | `desktop.py` settings / usage / provider configuration |

### 10. Schemas / Validation

| Schema 包 | 用途 |
|-----------|------|
| `schemas/book.py` | 导入与书籍 I/O |
| `schemas/scene.py` | 边界与场景分析结果 |
| `schemas/boundary_review.py` | 审阅 API |
| `schemas/reader_journey.py` | 旅程契约与版本常量 |
| `schemas/analysis_recovery.py` | 恢复计划 |
| `schemas/settings.py` | 桌面/云设置 |

---

## 依赖（声明）

见根 `pyproject.toml`：FastAPI、SQLAlchemy、Pydantic、httpx、tenacity、keyring、python-docx、ebooklib、beautifulsoup4 等。  
Python：`>=3.11,<3.13`。
