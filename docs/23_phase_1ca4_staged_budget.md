# 23｜Phase 1C-A.4 分阶段预算与可恢复执行

## 1. 原 409 根因

创建云端任务时，首次 Reservation 使用：

```text
worst_requests = 2 * (detection_batches + adjudication_batches + expected_scenes)
required_tokens = worst_requests * cloud_max_output_tokens_per_request(2000)
```

对约 68 段章节得到 required=98 请求 / 196000 Token，超过当日剩余 70 / 93011。  
费用未超。Gate `#70` 在创建 Run 之前拒绝，故无 Run、无 Invocation、无活动 Reservation。

根因：**Stage 1 错误地把尚未确认的 Scene Analysis 计入首次预留**。

## 2. Stage 1 预算范围

仅覆盖 `boundary_review_generation`：

- 正式段落与 Transition；
- `TransitionBatchPlanner`（v3.5）检测批次数；
- 裁决批次数（最坏：全部 transition 作为候选）；
- 每批初始 + 最坏 Repair；
- 输入/输出 Token 与费用估算。

**禁止**包含 `expected_scenes`、Scene Analysis、Evidence 分析。

同条件 68 段示例（估算，estimated=true）：

- detection_batches ≈ 10，adjudication_batches ≈ 1
- worst_case_requests ≈ 22（旧值 98）
- worst_case_tokens ≈ 29k（旧值 196k）

## 3. Stage 2 预算范围

边界确认并生成最终 Scene 后：

- 按真实 Scene 数量与每 Scene 字符估算 Analysis；
- 每 Scene 初始 + 最坏 Repair；
- 独立 `scene_analysis` Reservation。

不再重跑检测/裁决/审阅。

## 4. Reservation 生命周期

```text
Stage1 reserve → 候选生成 → awaiting_boundary_review 前释放
人工审阅期间：无活动 Stage1 Reservation
确认边界 → Stage2 reserve → Scene Analysis → 释放
Stage2 不足：boundary_confirmed_budget_blocked（保留 Revision/Scene）
resume-scene-analysis → 重新 Stage2 preflight/reserve
```

字段：`stage`、`expected_requests`、`worst_case_requests`、`released_at`；同一 Run 可有多条历史 Reservation（去掉 run_id 唯一约束）。

## 5. 可恢复状态

`boundary_confirmed_budget_blocked`：

- 不删除 Revision / Scene；
- 不要求重新生成候选；
- 任务中心可「继续 Scene Analysis」。

## 6. API

- `POST /analysis-runs/preflight`：Stage1 明细 + remaining + exceeded_dimensions
- `POST /chapters/{id}/analysis-runs`：Stage1 Reservation；409 返回结构化明细
- `GET /boundary-reviews/{id}/scene-analysis-preflight`：Stage2 估算
- `POST /boundary-reviews/{id}/confirm`：可返回 `budget_blocked=true`（仍 200）
- `POST /analysis-runs/{id}/resume-scene-analysis`：幂等恢复 Stage2

## 7. UI

- StartAnalysisDialog：Stage1 预算卡、「不包含 Scene Analysis」、维度不足文案
- BoundaryReviewPanel：确认前 Stage2 预览；不足仍可确认
- TasksPage：新状态中文；阻塞详情；继续按钮

## 8. 用量 vs Reservation

用量只统计 `http_request_sent=true` 的云端 Invocation。  
Reservation 是并发占用，不是实际消费；usage summary 区分 used / reserved / available。

## 9. PID 治理

`runtime_schema_version=1c-a-4`。启动后用端口 OwningProcess 反查并校验 uvicorn/`app.main:app`。  
stop 优先读 PID 文件，无效则按端口+命令行安全查找，避免误杀。

## 10. 用户测试流程（手动，需同意费用）

1. 重启 `start_storylens_dev.ps1`，确认 runtime PID 与监听一致。  
2. 云端选章 → 查看 Stage1 预览（应远低于旧 98/196000）。  
3. 创建任务 → awaiting_boundary_review；确认无活动 Stage1 Reservation。  
4. 审阅确认 → 若预算足则 Scene Analysis；若不足则 blocked → 调预算后 resume。  
5. 不提高预算绕过门禁；本阶段测试可用 Fake Provider 离线回归。
