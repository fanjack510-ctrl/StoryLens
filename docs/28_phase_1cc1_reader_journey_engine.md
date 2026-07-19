# Phase 1C-C.1｜Reader Journey Engine

## 架构

```
Chapter
└─ ReaderJourneyRun
   ├─ ReaderJourneyPhase
   │  └─ SceneReaderJourneyProfile
   │     └─ AnalysisEvidence（经 Artifact）
   └─ ChapterReaderJourneySummary
```

- 模型负责语义分析；程序负责 engagement、统计、阶段覆盖校验与结构化渲染数据。
- 建立在已确认 Scene + 已完成 Scene Analysis 之上，不重新切分 Scene。

## 数据模型

- `reader_journey_runs`：任务状态机、分阶段进度、失败指针、幂等 `client_request_id`
- `scene_reader_journey_profiles`：Scene 级阅读画像（分数、payload、engagement）
- `reader_journey_phases`：自适应连续阶段，硬合同 `1 <= phase_count <= min(6, scene_count)`（短章节允许 1—2；3—6 仅为较长章节建议）
- `chapter_reader_journey_summaries`：章级合成与确定性统计
- `reader_journey_revisions`：预留人工修订（本阶段未实现 UI）

迁移：`migrate_phase_1c_c1`（幂等索引 + `create_all`）

## Scene Profile

- Prompt：`packages/prompts/reader_journey_scene/v1.3`（v1.2/v1.1 仍可读；离线语义校准升级到 1.3）
- Schema：`SceneReaderJourneyBatchResult` / `SceneReaderJourneyProfileItem`（`scene_contract_version=1.3`）
- **v1.3 语义校准**：
  - Scene 2+ 的 `reader_question_in` 由前序活跃 `out` **确定性注入**（程序强制，不依赖模型）
  - 禁止整章全部 Scene `q_in` 为空
  - Hook 结构字段：`known|gap|continue_drive|next_handoff`
  - Payoff 扩展：`horror_payoff`、`stage_completion`
  - 连续无 payoff → 自动写入 `consecutive_no_payoff` 风险
  - `deterministic_statistics.journey_nodes`：短 Scene（≤3段）标为 `beat`，≤5段为 `secondary`
- **v1.2 读者问题语义**：`reader_question_in` 仅 `carried_from_previous`；新建问题写入 `reader_question_created`；`reader_question_out` 必须含 `origin` 与 evidence；章节首 Scene 允许空 `reader_question_in`
- 批次：输出容量感知规划（`planner_version=1.1`），默认每批最多 2 个 Scene；长 Scene 单独成批
- 截断：取消同批 `truncation_retry`；多 Scene 批次确定性左右拆分（`batch_split_after_truncation`）；单 Scene 仍截断则 `JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED`
- `engagement_score` 由程序计算，模型不得输出

## Chapter Synthesis

- Prompt：`packages/prompts/reader_journey_chapter/v1.2`（v1.1/v1 仍可读）
- 输入仅为 Scene Profile 摘要，不含整章正文
- 输出 phases + question chain + pacing diagnosis
- Phase 硬合同：完整覆盖、无重叠、无空缺、顺序与 Scene 一致；不得为凑数量编造虚假阶段
- 禁止泛化措辞（层层剥开/推向高潮/成功确立/悬念迭起等）；违规则确定性重写诊断

## 离线语义校准

- `POST /api/v1/reader-journey-runs/{id}/semantic-recalibrate`
- 使用已有 Scene Profiles 重算 q_in 链、hook 结构、连续无兑现风险、journey_nodes、章级诊断与统计
- 零 HTTP / 零 Token / 零费用；不新建 JourneyRun；不删除历史 Invocation

## Engagement 公式

- 配置：`config/reader_journey_formulas.json`（version `1.0`）
- 默认悬疑权重：curiosity 0.25、tension 0.20、hook 0.20、payoff 0.15、information_gain 0.10、emotional_resonance 0.10、cognitive_load -0.10、dropoff_risk -0.15

## Evidence

- 所有技法、payoff、hook、信息变化等必须引用 Scene 内合法 `paragraph_id`
- 写入 `analysis_artifacts`（type=`reader_journey_scene_profile`）+ `analysis_evidence`

## 质量门禁

Scene 级与章节级校验见 `reader_journey_validation.py`，错误码包括 `JOURNEY_EVIDENCE_OUT_OF_SCOPE`、`JOURNEY_SCORE_DISTRIBUTION_SUSPICIOUS`、`JOURNEY_PHASE_COUNT_INVALID`、`JOURNEY_PHASE_SCENE_GAP`、`JOURNEY_PHASE_SCENE_OVERLAP`、`JOURNEY_PHASE_DUPLICATE_SCENE`、`JOURNEY_PHASE_ORDER_INVALID`、`JOURNEY_PHASE_RANGE_NONCONTIGUOUS`、`JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED` 等。

## 预算

- Stage1：`reader_journey_scene_profiles`（按新批次规划预留，含拆分最坏请求，完成后释放）
- Stage2：`reader_journey_chapter_synthesis`（Scene 全部完成后单独预留）
- Preflight 零 HTTP、零 Token

## 恢复

- 状态：`scene_profiles_partial` / `failed` 可 `resume`（同 JourneyRun，不新建）
- 旧版 v1.1 契约失败（如空 `reader_question_in`）：优先 `POST .../scene-profiles/offline-replay`（零 HTTP，从 `parsed_response_json` 迁移到 v1.2 并写入 Profile）
- 已完成 Profile 跳过，不重复调用
- 同 analysis_run + contract 主版本下，存在可恢复 Run 时 create 默认返回已有 Run

## API

- `POST /api/v1/analysis-runs/{run_id}/reader-journey/preflight`
- `POST /api/v1/analysis-runs/{run_id}/reader-journey`
- `GET /api/v1/analysis-runs/{run_id}/reader-journey`
- `POST /api/v1/reader-journey-runs/{id}/resume`
- `POST /api/v1/reader-journey-runs/{id}/scene-profiles/offline-replay`
- `POST /api/v1/reader-journey-runs/{id}/semantic-recalibrate`
- `GET /api/v1/reader-journey-runs/{id}/progress`
- `POST /api/v1/reader-journey-runs/{id}/cancel`
- `GET /api/v1/reader-journey-runs/{id}/export?format=json`

## 前端

- `AnalysisResultsPage`「生成读者旅程图」入口
- failed 醒目展示（错误码中文、failed_scene、Invocation、用量、是否可恢复）
- Preflight 预算、云端同意、进度、Phase/Profile 结构化预览、JSON 导出
- 存在 failed/partial 时默认推荐恢复，不推荐新建第三个 JourneyRun

## 后续旅程简图渲染

- 已由 Phase 1C-C.2 实现：见 `docs/29_phase_1cc2_reader_journey_visual_workspace.md`。
- `GET .../reader-journey` 返回 `visualization`；前端 SVG 工作台确定性渲染。
