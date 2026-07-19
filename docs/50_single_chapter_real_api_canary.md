# docs/50｜Single-Chapter Journey Real API Canary（Phase 1D-B2）

**性质：** 真实模型受控认证（会产生 HTTP / Token / 费用）  
**前置：** Phase 1D-B1 = `ENGINEERING_READY_FOR_REAL_CANARY` + 操作者授权

## 授权

必须存在当前世代的 `authorization-vN.json`（不得复用旧世代）。

字段：`operator_approved=true`、`operator_max_cost_cny>0`、批准说明。

## 配置

- Provider：`aliyun_qwen_plus`
- Model：`qwen3.7-plus`
- `allow_auto_route=false`
- 独立库：`artifacts/single-chapter-pipeline-certification/real-canary/canary-vN.sqlite3`
- 禁止写入 `data/storylens.db`

## 认证费用账本（v1.0.8+）

远程断连等 transport 失败且 Provider 未返回 usage 时：

- **不得**把 reported tokens 写成 0；
- 使用 `scripts/certification/conservative_usage_accounting.py` 计算 conservative upper bound；
- 仅 `accounting_status=unknown` 或累计 `certification_accounted_cost` 超 `max_cost` 时硬停止。

## Scene Analysis Provider 恢复（v1.0.9+）

单 Scene 传输重试耗尽且根因为可恢复 Provider 错误（如 `PROVIDER_REMOTE_DISCONNECT`）时：

- Run 进入 `awaiting_provider_recovery`（Circuit Breaker 冷却），**不得**半成功 `succeeded`；
- 已成功 Scene Analysis 永久复用；仅重试失败/未完成 Scene；
- 超限（`max_recovery_cycles` / `max_recovery_duration` / `max_cost`）后保留 `PROVIDER_REMOTE_DISCONNECT` 并最终失败；
- 401/403 与 Validation/Business 合同错误不得进入 Provider 恢复流程。

## 全局模型调用策略（v1.1.0+ / DEFECT-CANARY-015）

所有生产模型调用必须经过 `ModelInvocationBroker`：

- AnalysisRun 冻结的 `provider` / `model` 对 normal、transport retry、schema/json repair、structural repair、repair provider retry、provider recovery 全部继承；
- `auto_route=false` 时禁止 Flash/Max Fallback；偏离授权策略在发送前失败（`MODEL_INVOCATION_POLICY_VIOLATION` / `MODEL_UNAUTHORIZED_FALLBACK`）；
- disabled Provider 在发送前以 `MODEL_PROVIDER_DISABLED_PRECHECK` 失败，不得拖到 `PROVIDER_DISABLED`；
- 离线门禁：`scripts/check_model_invocation_policy.py` → `INVOCATION_POLICY_PASS`；
- 下一真实 Canary 前必须先通过 `real-invocation-path-qualification-preflight-v1.json`，不得直接签发 authorization-v12。

## Reader Journey Evidence 预算（v1.1.1+ / DEFECT-CANARY-016）

- 顶层 `evidence_paragraph_ids.maxItems` 保持 **16**；Prompt v1.6 明确最少充分证据 / 不得枚举全 Scene。
- 去重与拒越界后仍超 16 → 定向 Evidence 压缩 patch（禁止完整 Profile 重生成 / 禁止机械截取前 16）。
- 离线门禁：`scripts/check_reader_journey_output_budget.py` → `READER_JOURNEY_OUTPUT_BUDGET_PASS`。
- 不得 resume `phase-1db2-r11`；不得复用 `authorization-v12`；下一 Canary 使用 `real-canary-preflight-v13.json` + `canary-v13.sqlite3`。

## 运行

```powershell
.\.venv\Scripts\python.exe .\scripts\run_single_chapter_real_canary.py
.\.venv\Scripts\python.exe .\scripts\check_single_chapter_real_canary.py
```

## 结论枚举

- `REAL_CANARY_PASSED`
- `REAL_CANARY_FAILED`
- `REAL_CANARY_BLOCKED`
- `REAL_CANARY_ABORTED_BY_LIMIT`
