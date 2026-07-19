# 05 — AI Analysis Pipeline

## 完整链路

```
用户上传小说
    ↓
章节 / 段落解析（无模型）
    ↓
创建 AnalysisRun + 预算预检
    ↓
Boundary Detection（模型，可分批 checkpoint）
    ↓
Human Boundary Review（云端普通路径必经）
    ↓
Scene Analysis（每场景模型调用，可 partial / resume）
    ↓
Reader Journey（场景画像批次 + 章节综合）
    ↓
前端结果展示 / 导出
```

异步执行：`BackgroundTasks` → `execute_scene_pipeline` / `analyze_confirmed_review` / `execute_reader_journey`。

---

## Step 0 — 章节解析

| 项 | 说明 |
|----|------|
| **输入** | TXT/DOCX/EPUB 文件字节 |
| **Prompt** | 无 |
| **处理** | `extractors` + `domain/ingestion` 规则切章 |
| **输出结构** | Book / Chapter / Paragraph（稳定 `paragraph.id`） |
| **保存** | `books`, `chapters`, `paragraphs`, `import_diagnostics_json` |

---

## Step 1 — Boundary Detection

| 项 | 说明 |
|----|------|
| **输入** | 章节段落序列；按 window/batch 切片 |
| **Prompt** | `packages/prompts/scene_boundary/`（云端默认 **v3.5**；本地 profile 可能 v1/v2） |
| **可选裁决** | `scene_boundary_adjudication/v1` |
| **输出结构** | `SceneBoundaryResult` / Compact Transition v3.5 → 规范化 transition 列表 |
| **校验** | Pydantic + `generate_validated`（含 repair） |
| **保存** | `analysis_artifacts`（type `scene_boundary`）、`boundary_detection_batch_checkpoints`、`model_invocations` |
| **状态** | `boundary_candidates_running` → `awaiting_boundary_review`（assisted）或继续自动路径 |

---

## Step 2 — Boundary Review（人工）

| 项 | 说明 |
|----|------|
| **输入** | 候选 transitions + 用户 accept/reject/manual |
| **Prompt** | 无（人工） |
| **输出结构** | `BoundaryReviewDecision` 集合 → confirm 生成 `BoundaryRevision.final_boundaries_json` |
| **保存** | `boundary_review_sessions`, `boundary_review_decisions`, `boundary_revisions`, 新建 `scenes` |
| **后续** | confirm 后后台启动场景分析 |

---

## Step 3 — Scene Analysis

| 项 | 说明 |
|----|------|
| **输入** | 每个 Scene 的段落文本 + 元数据 |
| **Prompt** | `packages/prompts/scene_analysis/`（确认路径常用 **v3.2**；与 run 记录版本绑定） |
| **输出结构** | `SceneAnalysisResult`（含 evidence 字段 → paragraph_id） |
| **校验** | schema + 段落 ID 必须真实存在 |
| **保存** | `analysis_artifacts`（`scene_analysis`）、`analysis_evidence`；更新 `analysis_runs` 进度/状态 |
| **恢复** | resume / offline-replay / `awaiting_provider_recovery` / unified recover |

---

## Step 4 — Reader Journey

| 项 | 说明 |
|----|------|
| **输入** | 已成功的场景分析结果集合 |
| **Prompt** | `reader_journey_scene` **v1.6**；`reader_journey_chapter` **v1.2**；失败修复 `reader_journey_repair/v1` |
| **处理** | batch planner → 每场景画像 → 章节综合 → engagement/statistics → semantic recalibrate（可确定性） |
| **输出结构** | `SceneReaderJourneyProfileItem`、phases、`ChapterReaderJourneySynthesisResult` |
| **保存** | `reader_journey_runs`, `scene_reader_journey_profiles`, `reader_journey_phases`, `chapter_reader_journey_summaries`；artifact `reader_journey_scene_profile` |
| **展示** | 前端 CanonicalJourneyChart + SyncWorkspace + Inspector（无额外模型） |

---

## Step 5 — 结果展示与导出

| 渠道 | 说明 |
|------|------|
| UI | Scene 结构 / Evidence / Journey 曲线与指标 |
| API 导出 | `GET .../results/export`（json/markdown）；`GET .../reader-journey-runs/{id}/export` |
| 客户端 | Journey PNG（`exportJourneyPng.ts`） |

---

## 模型调用统一路径

```
Pipeline service
  → model_invocation_broker（策略门禁：冻结 provider/model）
  → ModelGateway / OpenAICompatibleProvider
  → structured_output.generate_validated
  → 写入 model_invocations + 业务表
```

普通模式正式支持：`aliyun_qwen_plus` / `qwen3.7-plus`；`auto_route=false`；Flash fallback 关闭。

## 成本与预算控制点

- Create / full-pipeline / resume / recover **preflight**
- 分阶段 `cloud_budget_reservations`
- 日额度 + run-scoped 临时请求授权（不永久改写日限额）
- 连接测试也有 preflight
