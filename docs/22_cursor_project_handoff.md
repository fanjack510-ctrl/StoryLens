# 22｜Cursor 项目接管文档（脱敏）

> 生成时间：2026-07-17（本地）  
> 范围：只读核验 + 离线测试 + 本文件  
> 生产代码修改：0｜真实模型请求：0｜新增云端 Token/费用：0

---

## 1. 产品目标

叙镜 StoryLens：面向小说作者与写作学习者的 AI 拆书、结构化分析与案例检索系统。

当前可交付目标（已实现的工程闭环）：

1. 导入 TXT / DOCX / EPUB，识别章节并建立稳定段落 ID；
2. 通过统一 Model Gateway 调用本地 OpenAI 兼容服务或阿里云百炼；
3. 生成场景边界候选（含拆批与二次裁决），经人工审阅后固化 Scene；
4. 对已确认 Scene 做结构分析（entry/goal/obstacle/actions/outcome 等）；
5. 所有文学结论绑定真实段落 ID；结果、Invocation、预算门禁可审计、可重跑；
6. Reader Journey：Scene Profile + Chapter Phase + 离线语义校准 + **预测读者阅读旅程**可视化（`docs/29_phase_1cc2_reader_journey_visual_workspace.md`）。

明确未做：全书伏笔网络、图数据库、多模型投票、LoRA 训练、商业计费。

---

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+、FastAPI、SQLAlchemy、Pydantic v2、SQLite |
| 前端 | React 19、TypeScript、Vite 6、TanStack Query、Zustand |
| 桌面壳 | Tauri 2（开发可用 Vite `127.0.0.1:1420`） |
| 模型 | llama.cpp OpenAI 兼容；阿里云百炼 OpenAI 兼容 |
| 凭据 | OS keyring（CredentialStore）；测试用 Fake store |
| 质量 | pytest、ruff、vitest、Playwright、`scripts/check_project.py` |

根目录无 monorepo 级 `package.json`；前端包在 `apps/desktop/package.json`。

---

## 3. 目录结构（要点）

```text
D:\Dstorylens
├── AGENTS.md / README.md / pyproject.toml
├── apps/api/app/          # FastAPI 应用
│   ├── api/v1/            # books、analysis、desktop、boundary_reviews
│   ├── db/                # models + 幂等迁移
│   ├── model_gateway/     # Gateway + OpenAICompatibleProvider
│   ├── schemas/           # Pydantic 契约
│   └── services/          # 流水线、预算、审阅、适配器
├── apps/desktop/src/      # React 工作台
├── packages/prompts/      # 版本化 Prompt
├── config/                # pricing example / local profiles example
├── data/                  # storylens.db、runtime（gitignore）
├── docs/                  # 设计与阶段文档
└── scripts/               # 启动/停止/检查/冒烟（收费探测脚本存在但本轮禁用）
```

---

## 4. 核心数据模型

| 实体 | 职责 |
|---|---|
| Book / Chapter / Paragraph | 导入产物；Paragraph 主键为稳定段落 ID |
| AnalysisRun | 任务状态机；云端需 `execution_mode` + `cloud_consent` |
| Scene | 正式场景；可关联 `boundary_revision_id` / `boundary_source` |
| AnalysisArtifact / AnalysisEvidence | 结构化结果与段落证据链 |
| ModelInvocation | 每次模型调用审计（可关闭 raw；云端记 Token/费用） |
| RequestGateDecision | 预算/门禁审计快照 |
| CloudBudgetReservation | 创建云端 Run 前的额度预留 |
| ProviderConfiguration / ApplicationSetting | 非密钥配置与全局设置 |
| BoundaryReviewSession / Decision / Revision | Phase 1C-A 人工边界审阅 |

迁移：启动时幂等 `migrate_phase_1b` … `migrate_phase_1c_a3` + `create_all`。

---

## 5. 导入与章节解析

- 提取器：TXT / DOCX / EPUB（`extractors` + `domain/ingestion`）。
- TXT：UTF-8 / UTF-8-SIG / GB18030 / UTF-16；无空格中文章节标题评分采纳。
- 预览：`/books/chapter-detection/preview`；源字节可存库以支持事务性 reparse。
- 有成功 AnalysisRun 时禁止破坏性替换结构。
- 段落 API 支持分页（limit≤500）。

---

## 6. Scene Boundary 架构演进

| 版本 | 要点 |
|---|---|
| v1–v2 | Canonical `SceneBoundaryResult`；早期契约漂移 |
| v3 / v3.1 | `response_contract` 注入 Schema；输出 Token 策略修正 |
| v3.2 | Transition 列表协议 |
| v3.3–v3.4 | Compact Provider DTO + 适配器；`TransitionBatchPlanner` 拆批 |
| **v3.5（现行）** | 第一遍只产 `boundary_candidate`；证据由程序固定；第二遍 `scene_boundary_adjudication/v1` |

冻结结论（文档与能力标记）：工程与 Scene Analysis 就绪；**自动边界路由未就绪** → Phase 1C-A 人工审阅。

---

## 7. Scene Analysis 架构

- 正式 Prompt：`scene_analysis/v3.1`。
- Schema：`SceneAnalysisResult`（EvidenceField + function_tags 等）。
- 用户小说路径：仅 Review `confirmed` 且 Scene 覆盖率 100% 后进入；否则 `BOUNDARY_REVIEW_REQUIRED`。
- v3.5 流水线在候选生成后 `create_review_session` 并 **停止**，不自动跑 Scene Analysis。
- Fixture/旧 automatic 路径仍可在无审阅门禁时直接分析（离线测试）。

---

## 8. Model Gateway

- `ModelGateway` 按名路由；业务代码不写死厂商 SDK。
- `OpenAICompatibleProvider`：本地与阿里云共用。
- Registry 注册：`local_llama`、profile 本地模型、`aliyun_qwen_plus|max|flash`。
- Plus：`supports_boundary_candidates=true`，`automatic_boundary_routing=false`，`requires_boundary_review=true`，`default=false`。

---

## 9. Provider 能力（核验时脱敏状态）

| Provider | 核验摘要 |
|---|---|
| aliyun_qwen_plus | enabled、connected、手动边界资格 eligible；`allow_auto_route=false` |
| aliyun_qwen_max / flash | 未作手动边界候选角色；配置侧未启用 |
| local_* | 开发机上健康检查为未运行/禁用；不参与云端审阅流 |

能力契约版本：`capability_schema_version = 1c-a-2`。

---

## 10. 云端预算与安全

- 全局云端开关 + 每次 Run 的 `cloud_consent` 双门。
- API Key：环境变量 / keyring；禁止进源码、日志、响应。
- 预算字段：日请求/Token/费用上限、单请求输出硬上限、未知价格停止等。
- `daily_usage` 只统计 `is_cloud && http_request_sent`。
- 创建云端 Run 前 `reserve_budget`；失败写 `RequestGateDecision` 并抛 `INSUFFICIENT_BUDGET_RESERVATION`（**不创建 Run**）。
- 价格：本机 `config/cloud_pricing.json`（不入库；example 在仓库内）。

---

## 11. Phase 1C-A 人工审阅流程

```text
导入 → 选章 → StartAnalysisDialog（cloud + consent）
→ preflight → POST analysis-runs（assisted_boundary_review）
→ 边界候选检测（拆批）→ 候选裁决（拆批）
→ awaiting_boundary_review + BoundaryReviewSession
→ 用户接受/拒绝/新增 → confirm → BoundaryRevision + Scene
→ Scene Analysis → Artifact/Evidence → succeeded
```

前端入口：`StartAnalysisDialog`、`BoundaryReviewPanel`、任务中心轮询。

---

## 12. 当前正式 Prompt / Schema

| 任务 | Prompt | Provider DTO / Schema |
|---|---|---|
| Boundary Candidate | `scene_boundary/v3.5` | `CompactTransitionClassificationResultV35`（contract 3.5） |
| Adjudication | `scene_boundary_adjudication/v1` | `BoundaryCandidateAdjudicationResult`（1.0） |
| Scene Analysis | `scene_analysis/v3.1` | `SceneAnalysisResult` |
| Canonical 边界 | （适配器产出） | `SceneBoundaryResult` |

Schema hash（SHA-256 前缀，完整 hash 可本地用 `contract_hash` 复算）：

- v3.5 provider：`4cd45c0d44c2aa83…`
- adjudication：`fc11bb1bd4dc8cd2…`
- scene analysis：`bb88f1bc0a55f7d7…`
- canonical boundary：`121b0ba66dfc4ed5…`

输出策略：`CloudTaskOutputPolicy`（Boundary/Adjudication 768、Analysis 1600、repair 分档）；与用户硬上限比较。截断 → 同 Provider 整次重生成，不续写。

Repair：JSON/Schema → Flash 可修；Evidence/业务 → 主 Provider；单任务最多两次调用。

---

## 13. 当前 API（摘要）

- Books：import / list / chapters / paragraphs / reparse / chapter-detection preview
- Analysis：`POST /analysis-runs/preflight`，`POST /chapters/{id}/analysis-runs`，runs CRUD/retry，scenes/artifacts/invocations
- Providers：list + configuration/connect、零生成 transport-diagnostic、真实 test preflight + `confirmed=true` 单次最小 JSON 测试
- Settings：`/settings/cloud`，`/settings/cloud-budget`，`/cloud-usage/summary`，`/cloud-pricing/status`，desktop settings
- Boundary：chapter review、decide、manual add、confirm、preview、后续 analyze
- System：`/health`，`/api/v1/system/capabilities` → `1c-a-2`

---

## 14. 当前前端入口

| 路由 | 页面 |
|---|---|
| `/` | Home |
| `/library` | 书库导入 |
| `/books/:bookId` | 三栏工作台 + 开始分析 + 审阅面板 |
| `/tasks` | AnalysisRun 中心 |
| `/providers` | 模型配置 |
| `/settings` | 云端开关/预算/桌面偏好 |
| `/cases` | 占位 |

服务层：`apiClient`、`analysisApi`、`providersApi`、`booksApi`、`settingsApi`、`providerEligibility`。

---

## 15. 当前测试基线（本轮已执行）

| 检查 | 结果 |
|---|---|
| `bootstrap_windows.ps1 -SkipInstall` | 通过（提示 legacy `.env` 变量名） |
| `check_env.py` / `check_project.py` | 通过 |
| `pytest` | **149 passed** |
| `ruff check apps/api scripts` | 通过 |
| desktop `typecheck` / `lint` / `vitest` / `build` / `test:e2e` | 全部通过（43 unit + 2 e2e） |
| `PRAGMA integrity_check` | `ok` |

未执行（本轮禁止）：`probe_aliyun_qwen.py`、真实 health 外探、calibrate、创建付费 Run。

---

## 16. 当前冻结状态

- `allow_auto_route` 必须保持 `false`；Plus `default=false`。
- `automatic_boundary_routing_ready=false`；`assisted_boundary_review_ready=true`。
- Phase 1C-A.4（分阶段预算）**已诊断、未实施**。
- 不得删除历史 Run / Invocation / Artifact / Revision。

---

## 17. 当前唯一阻塞问题

> **Phase 1C-A.4 已实施（见 `docs/23_phase_1ca4_staged_budget.md`）**。同条件 68 段 Stage 1 最坏约 22 请求 / ~29k Token，低于历史剩余 70 / 93011。

历史 Gate `#70`（归档）：required 98 / 196000；remaining 70 / 93011；维度 requests+tokens；首次预留错误包含 Scene Analysis。

## 18. 下一阶段建议

1. ~~Phase 1C-A.4 分阶段 Reservation~~（已完成）
2. ~~Phase 1C-A.5 Provider 传输诊断与错误分类~~（已完成，见 `docs/24_phase_1ca5_provider_transport.md`）
3. ~~Phase 1C-A.6 真实连接测试确认、状态分离与 Invocation 审计~~（已完成，见 `docs/25_phase_1ca6_provider_connection_test.md`）
4. ~~Phase 1C-A.7 人工语义冲突容错、Detection检查点和失败Run恢复~~（已完成，见 `docs/26_phase_1ca7_review_conflicts_and_checkpoints.md`）
5. ~~Phase 1C-A.10 Scene Analysis 运行时装配与断点续跑~~（已完成，见 `docs/27_phase_1ca10_scene_analysis_resume.md`）
6. 用户确认费用后扩大审阅样本统计
7. 清理 `.env` legacy 变量名为 `STORYLENS_*`
8. 可选：用量面板强化 used / reserved / available 可视化

## 19. 禁止破坏的架构约束

1. 模型输出必须 Pydantic 校验；结论必须引用真实段落 ID。
2. Provider 不得写死在领域业务代码；本地/云端统一协议。
3. API Key / Authorization / 完整 Workspace ID / 完整专属 Base URL 不得进源码、日志、文档样例、测试样本。
4. 失败任务可重试、可定位、可单项重跑；历史审计不可静默覆盖删除。
5. Plus 不得擅自 `default=true` 或 `allow_auto_route=true`。
6. 不引入 Neo4j、微服务拆分、LoRA 训练等超阶段复杂度。
7. 收费探测与整本分析必须用户显式确认；默认测试走 Fake Provider。

---

## 附录 A｜本轮运行时核验摘要

| 项 | 值 |
|---|---|
| :8000 | 监听中（python）；capabilities=`1c-a-2`；health ok；`default_provider=none` |
| :1420 | 监听中（node/Vite） |
| runtime PID 文件 | `backend.json` 记录 PID 与当前监听 PID **不一致**（运维陈旧记录） |
| 代码时间 vs 进程启动 | `analysis.py` mtime 早于当前 8000 进程启动 → 进程加载含预留公式的现行代码 |
| DB | `data/storylens.db`；integrity ok |
| 今日用量（UTC 日） | requests 80 / tokens 106989 / cost ≈0.324；剩余 70 / 93011 / ≈2.676 |
| 预算设置 | daily req 150，token 200000，cost 3.0 CNY；max output/req 2000；max req/run 10 |
| max IDs | Run 51，Invocation 89，Gate 70，Reservation 8（均已 released） |
| BoundaryReviewSession | count 0（用户正式审阅尚未成功创建） |

## 附录 B｜未找到的要求文件

- 仓库根目录 `package.json`：**不存在**（前端独立于 `apps/desktop`）。
)
