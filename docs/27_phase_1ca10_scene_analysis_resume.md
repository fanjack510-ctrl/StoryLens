# Phase 1C-A.10｜Scene Analysis 断点续跑与 Provider 运行时装配

## 1. Run #55 根因（只读核验）

Run #55 在 Boundary Review 确认后进入 Scene Analysis，于首个 Scene（id=6）**HTTP 发送前**失败：

- `error_code=SCENE_ANALYSIS_FAILED`
- 真实根因：`PROVIDER_DISABLED`（Invocation #105/#106，`audit_type=pre_send_failure`）
- Stage 1 Detection 路径会调用 `bind_gateway_runtime` / `apply_provider_runtime`，把 DB 中 `ProviderConfiguration.enabled=true` 覆盖到运行时
- Stage 2 `analyze_confirmed_review` 原先**未**做同一装配；进程重启后 registry 云 Provider 恢复默认 `enabled=false`，于是 Stage 2 被拒绝
- 失败落库不完整：`root_error_message` / `failed_invocation_id` 为空

约束：不自动恢复 Run #55；不重建 Revision #1 与 Scene #6–19。

## 2. Provider 运行时装配

`ProviderRuntimeService.resolve_for_run(run, task_type, ...)`：

1. 绑定 gateway 全部 Provider（DB + CredentialStore）
2. 覆盖 enabled / base_url / timeout / model
3. 计算零费用资格（云开关、pricing、budget、scene_analysis 能力）
4. 返回 `provider_state_version`
5. **不**发外部请求、**不**创建 Invocation、**不**输出凭据

Detection、Adjudication、Scene Analysis、resume、恢复 Run、正式生成路径统一经此服务。  
**不得**要求 `default=true` / `allow_auto_route=true`。

## 3. Scene 级完成判定

`scene_analysis_progress`：有效 `scene_analysis` Artifact（`validation_status=valid`）且至少 1 条 Evidence，才算完成。  
不依据 HTTP 200 判定完成。

返回：`total/completed/remaining`、`pending_scene_ids`、`boundary_revision_id`、`coverage_rate`。

## 4. Stage 2 恢复流程

- `GET|POST /api/v1/analysis-runs/{id}/resume-scene-analysis/preflight`：零费用预算与资格预览
- `POST /api/v1/analysis-runs/{id}/resume-scene-analysis`：同一 Run 续跑

允许状态：`boundary_confirmed`、`boundary_confirmed_budget_blocked`、`failed`+`failed_stage=scene_analysis`、`scene_analysis_partial`。

语义：复用 Revision/Scene；跳过已完成 Artifact；新建 Stage 2 Reservation；`client_request_id` 幂等；并发返回 `SCENE_ANALYSIS_ALREADY_RUNNING`。

## 5. 部分完成语义

每 Scene 独立 `commit`。中途失败：

- 已完成 Artifact/Evidence **保留**
- Run → `scene_analysis_partial`（或 `failed` 且 completed=0）
- 下次 resume 只处理 remaining

## 6. Reservation

Stage 2 独立 Reservation；成功或失败均 `release`。无活动悬挂。

## 7. 错误落库

外层可保留 `SCENE_ANALYSIS_FAILED`，必须同时写入：

`root_error_code/message`、`exception_type`、`transport_kind`、`retryable`、`failed_invocation_id`、`failed_scene_id/index`、`user_action_hint`、`failure_details`（含 completed/remaining）。

## 8. UI

任务详情：

- Detection 恢复卡仅当 `detection_recovery_available && remaining_detection_batch_count > 0`
- Scene 失败显示「Scene Analysis可继续」卡 + 预算预览 + 云端同意 +「继续Scene Analysis」
- 审阅 confirmed 后不再显示「全部确认」/ incomplete 提示

## 9. 用户手动恢复 Run #55 步骤

1. 确认「模型与API」中 Plus `enabled=true`、云端总开关开启、预算充足  
2. 打开任务中心 → Run #55 → 查看详情  
3. 确认显示 Scene 恢复卡（0/14），**无** Detection「从已有结果继续」  
4. 勾选云端同意 → 查看预算 → 点击「继续Scene Analysis」  
5. 等待同一 Run #55 进入 `scene_analysis_running` → `succeeded`  

本阶段自动化测试与离线验证**不得**替用户点击恢复，**不得**发送真实阿里云请求。

## 10. Phase 1C-A.10.2 补充（Run #55 卡在 Scene#10）

根因：单段 Scene 触发 `validate_scene_analysis` 的“整段无差别引用”规则误杀；三次 resume 均付费重试同一 Scene。

修复：
- 单段 Scene 跳过该规则；
- `POST .../replay-scene-analysis-offline` 从已有 parsed 响应写 Artifact（零 HTTP）；
- 每 Scene HTTP 尝试上限；同 `client_request_id` 失败后幂等；
- 任务列表显示 `Scene Analysis：completed / total`。

Run #55：已对 Scene#10 离线重放成功（5/14），**不得**再盲目点击继续；剩余 9 个 Scene 需用户明确确认后再 resume。
