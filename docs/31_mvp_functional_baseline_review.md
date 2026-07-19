# docs/31｜StoryLens MVP 最小功能闭环复盘与核心代码冻结

**阶段：** Phase 1C-C.2.2-Baseline  
**性质：** 只读复盘 + 冻结清单；**不修改生产代码**；**不执行** Phase 1C-C.2.3 Single-Page Chapter Analysis Workspace。  
**生成依据：** 当前代码 import/路由、`data/storylens.db` 只读核验、本机离线测试重跑（非历史报告摘抄）。

配套产物：

- `audits/mvp-functional-baseline-v1/core-freeze-manifest.json`
- `audits/mvp-functional-baseline-v1/dependency-map.md`
- `audits/mvp-functional-baseline-v1/database-baseline.json`
- `audits/mvp-functional-baseline-v1/test-baseline.json`
- `audits/mvp-functional-baseline-v1/ui-change-boundary.md`
- 只读脚本：`_readonly_audit.py`、`_generate_freeze_manifest.py`

---

## 1. 当前最小功能闭环（真实实现）

MVP 主链在工程上已闭环，但是**多页面人工接力**，不是单页面自动工作流。

| 步骤 | 用户可见 | 当前实现位置 |
|------|----------|--------------|
| 1 导入书籍 | `/library` | `book_service` + extractors + ingestion |
| 2 选择章节 | `/books/:id` | `BookWorkspacePage` |
| 3 启动分析 | StartAnalysisDialog → `/tasks` | `POST .../analysis-runs` |
| 4 审阅 Scene 边界 | BoundaryReviewPanel | `awaiting_boundary_review` → confirm |
| 5 查看分析结果 | `/analysis-runs/:id/results` | structure/evidence/overview |
| 6 查看读者旅程 | results `tab=reader-journey` | 显式创建 JourneyRun + SyncWorkspace |
| 7 正文↔旅程联动 | SyncWorkspace | `useJourneySelection` + TextPane |
| 8 导出 | JSON/MD/PNG | results export + `exportJourneyPng` |
| 9 失败恢复 | `/tasks` + journey 面板 | resume / offline replay / checkpoints |

**未完成（勿写成已完成）：** 单页面章节分析工作区、自动串联 Reader Journey、ChapterAnalysisWorkflow 表。

---

## 2. 三级路线图

### 2.1 第一级：用户可见能力

1. 导入 TXT/DOCX/EPUB 并建立稳定段落 ID  
2. 浏览章节正文  
3. 创建云端/本地分析任务（含 consent 与预算预检）  
4. 人工边界审阅与确认  
5. Scene Analysis 结果浏览与 Evidence 定位  
6. Reader Journey 生成、进度、失败恢复  
7. Visualization 1.1 曲线 / Phase / Cluster / Hook-Payoff  
8. 正文–旅程双向定位与 URL 状态恢复  
9. JSON / Markdown / PNG 导出  
10. Detection / Scene Analysis / Journey 的 resume 与 offline replay  

### 2.2 第二级：业务服务

| 服务 | 核心文件 |
|------|----------|
| ingestion | `extractors.py`, `domain/ingestion.py`, `book_service.py` |
| chapter extraction | 同上 + `schemas/book.py` |
| scene pipeline | `scene_pipeline.py`, adapters, adjudicators |
| boundary review | `boundary_review_service.py`, `boundary_reviews.py` |
| scene analysis | `boundary_review_service.analyze_confirmed_review`, `scene_analysis_*` |
| structured output | `structured_output.py`, `prompt_service.py` |
| provider gateway | `model_gateway/*`, `provider_runtime_service.py` |
| budget / reservation | `staged_budget.py`, `budget_reservation.py` |
| reader journey | `reader_journey_pipeline.py`, validation, batch planner |
| semantic calibration | `reader_journey_semantic_calibrate.py` |
| visualization | `reader_journey_visualization.py`, `reader_journey_visual_calibration.py` |
| export | `scene_results_service.py`, `scene_results_export.py` |
| recovery | checkpoints, offline replay, resume endpoints |

### 2.3 第三级：核心代码文件（摘要）

完整 sha256 清单见 `core-freeze-manifest.json`。每项冻结记录含：path、category、interfaces、tests。

代表性内核：

| 路径 | 主要符号 | 输入→输出 | 持久化 | 失败态 | 冻结 |
|------|----------|-----------|--------|--------|------|
| `db/models.py` | ORM 表 | — | 全部核心表 | — | CORE |
| `scene_pipeline.py` | `execute_scene_pipeline` | Chapter→边界/审阅 | Run/Artifact/Scene | failed_* / awaiting_review | CORE |
| `structured_output.py` | `generate_validated` | Prompt+Schema→模型 | ModelInvocation | SCHEMA/JSON/BUSINESS | CORE |
| `reader_journey_pipeline.py` | `execute_reader_journey` | Scenes→Profiles+Summary | Journey* 表 | partial/failed/budget_blocked | CORE |
| `reader_journey_visual_calibration.py` | level/hook/payoff/cluster | Profiles→viz 1.1 | 无写库 | — | CORE |
| `schemas/reader_journey.py` | contract pins | — | — | 校验错误码 | CONTRACT |
| `useJourneySelection.ts` | URL 状态机 | searchParams↔selection | URL | — | REUSABLE_UI |
| `ReaderJourneySyncWorkspace.tsx` | 分屏编排 | viz+paragraphs | — | ErrorBoundary | REUSABLE_UI |

依赖图详见 `dependency-map.md`。

---

## 3. 数据库只读核验（当前）

来源：`audits/mvp-functional-baseline-v1/database-baseline.json`

| # | 项 | 结果 |
|---|----|------|
| 1 | Book | 5 |
| 2 | Chapter | 2101 |
| 3 | Paragraph | 188397 |
| 4 | AnalysisRun | 55；succeeded=42，failed=13 |
| 5 | Run #55 | **succeeded**；provider=`aliyun_qwen_plus`；prompt=`v3.5`；chapter subject_id=2 |
| 6 | BoundaryRevision #1 | 存在；run=55；coverage_rate=1.0 |
| 7 | Scene #6–19 | **完整 14**；ordinal 1–14 |
| 8 | Scene Analysis Artifact (run55) | 14（valid 14） |
| 9 | Evidence (run55 scene_analysis) | 130；**非法 0** |
| 10 | ReaderJourneyRun | 2；failed=1，succeeded=1 |
| 11 | JourneyRun #2 | **succeeded**；scene contract **1.3**；prompt v1.3 |
| 12 | Scene Profile (#2) | 14 |
| 13 | Phase (#2) | **4** |
| 14 | Chapter Summary (#2) | 1 |
| 15 | Visualization | 可离线生成；version **1.1** |
| 16 | Question Chain | 8（summary JSON） |
| 17 | Question Cluster | **11**（visible default **5**） |
| 18 | ModelInvocation 总数 | 149 |
| 19 | 活动 Reservation | **0** |
| 20 | 孤立 Reservation | **0**（leaked active 亦 0） |
| 21 | 重复 valid Artifact | 无 |
| 22 | 重复 Profile | 无 |
| 23 | foreign_key_check | `[]` |
| 24 | integrity_check | **ok** |

**记录缺口（报告，不修复）：** JourneyRun #2 存储的 `chapter_prompt_version=v1`、`chapter_contract_version=1.0`，落后于代码默认 v1.1 / 1.1；场景侧已校准到 1.3。

---

## 4. Run #55 / JourneyRun #2 黄金样本

离线核验 **33/33** 通过（`_readonly_audit.py`）。要点：

- Chapter 2 正文 68 段完整（P0001–P0068）
- Scene 覆盖率 100%；无遗漏；无重叠；顺序正确
- Scene Analysis 14/14；Evidence 全部合法且落在 Scene 范围内
- Profiles 14/14；Phase 覆盖 1–14 无重叠
- engagement 曲线 14 点；Core/Secondary/Beat = **6/5/3**
- visible Hook=8；visible Payoff=7；Cluster=11；默认可见 Cluster=5
- Scene 14 = core；Scene 1/14 详情可序列化
- `writing_takeaways` 在 **visualization.scene_nodes**（详情抽屉）；**不在** `scene_profiles` 摘要 DTO（前端兼容：读 node 字段）
- PNG 数据源 / JSON / Markdown / Journey JSON 均可离线生成
- URL 恢复契约：`tab/mode/scene/paragraph/metric/cluster`（E2E 覆盖）

禁止本阶段重跑模型；本审计 **HTTP 模型请求=0，Token=0，费用=0**。

---

## 5. 离线回归测试基线

| 检查 | 结果 |
|------|------|
| check_project | passed |
| pytest | **271 passed** |
| ruff | passed |
| typecheck | passed |
| eslint | passed |
| vitest | **111 passed** |
| build | passed |
| Playwright e2e | **19 passed**（Fake/mock，无真实阿里云） |
| SQLite integrity | ok |
| FK | [] |

Fake/E2E 覆盖导入→边界→分析→旅程→校准→可视化→Sync→定位→导出，以及失败/截断/offline replay/resume/幂等/URL 刷新。详见 `test-baseline.json`。

---

## 6. 核心冻结分类与数量

| 类别 | 数量 |
|------|------|
| FROZEN_CORE | **60** |
| FROZEN_CONTRACT | **15** |
| REUSABLE_UI_LOGIC | **15** |
| UI_SHELL_CHANGEABLE | **16** |

Manifest：`core-freeze-manifest.json`（含 sha256）。

---

## 7. API / 数据契约冻结要点

禁止静默变更：

- Paragraph / Scene / Phase / Evidence ID 语义
- AnalysisRun / ReaderJourneyRun 状态枚举与错误码
- `SceneAnalysisResult` / Journey Profile contract **1.3** / Visualization **1.1**
- 版本字段：`prompt_version`、`scene_contract_version`、`visualization_version`、formula versions
- 前端 `types/*` 与 `analysisApi` 路径语义

允许 UI 只读消费；变更须单独立项。

---

## 8. 后续 UI 改造边界

见 `ui-change-boundary.md`。

结论摘要：

- **不需要** 为单页面先建 `ChapterAnalysisWorkflow` 表；可用现有 Run 聚合。
- 书页可 **composition 嵌入** `ReaderJourneySyncWorkspace`（纯 UI），但 journey 仍须已有 succeeded + visualization。
- 旧 `/analysis-runs/:id/results` 必须保留兼容。
- 边界确认、consent、预算恢复、journey 启动仍为人工节点。

---

## 9. 风险与缺口（带确认级别）

| # | 项 | 级别 | 说明 |
|---|----|------|------|
| 1 | 已闭环能力（多页主链） | **confirmed** | 代码+DB+测试+黄金样本 |
| 2 | Fake 全链回归 | **confirmed** | 本轮 pytest/e2e |
| 3 | 真实云端稳定性（非 Run55） | **partially_confirmed** | 仅黄金样本与历史 runs；非普适证明 |
| 4 | 依赖 Run #55 特例的视觉数字（6/5/3, hook8…） | **confirmed**（样本） / **known_risk**（外推） | 公式冻结；其他章节数值会变 |
| 5 | 人工节点 | **confirmed** | consent、边界确认、journey 启动、预算恢复 |
| 6 | 真实费用节点 | **confirmed** | 云端 boundary/analysis/journey 调用 |
| 7 | 恢复链限制 | **confirmed** | blind_resume_blocked；需 offline replay；attempt limit |
| 8 | UI 重构最易破坏 | **known_risk** | scroll spy、URL 参数、evidence 定位、testid、safeRender |
| 9 | 重复页面/状态 | **confirmed** | Library vs WorkspaceLanding；Results 经典三栏 vs Sync 全页切换；Tasks vs Results 内恢复入口 |
| 10 | 可删纯 UI | **partially_confirmed** | Home/Cases 占位；需产品确认 |
| 11 | 不可删入口 | **confirmed** | library/books/tasks/results/providers/settings |
| 12 | Journey #2 chapter 版本落后代码默认 | **confirmed** | 存储 v1/1.0 vs 代码 v1.1/1.1；不修复于本阶段 |
| 13 | 工作区非 git 仓库 | **confirmed** | 无法记录 git_commit；manifest 标 `not_a_git_repository` |
| 14 | 自动串联分析→旅程 | **unverified / not implemented** | 非本阶段范围 |
| 15 | writing_takeaways 不在 profile 摘要 DTO | **confirmed** | 详情走 visualization nodes；属契约形状差异，非数据缺失 |

级别定义：`confirmed`=本轮代码或数据直接支持；`partially_confirmed`=部分支持；`unverified`=未在本轮证明；`known_risk`=已知破坏面。

---

## 10. UI 阶段建议

**建议进入 UI 优化（壳层与信息架构），但暂缓 Phase 1C-C.2.3 大规模单页重写，直到：**

1. Core Freeze 检查脚本纳入提交门禁；  
2. 明确旧路由兼容方案；  
3. 不引入新工作流表；  
4. 每轮 UI PR 复跑 Fake 测试 + Run #55 只读黄金样本。

---

## 11. 本轮不变式（验收）

| 项 | 值 |
|----|----|
| 真实模型请求 | **0** |
| Token | **0** |
| 费用 | **0** |
| 新建 JourneyRun #3 | **否** |
| Run #55 | **succeeded**（未改） |
| JourneyRun #2 | **succeeded**（未改） |
| 生产代码修改 | **无** |
| 现有测试修改 | **无** |
| 数据库写入 | **无** |
| Phase 1C-C.2.3 | **未执行** |
