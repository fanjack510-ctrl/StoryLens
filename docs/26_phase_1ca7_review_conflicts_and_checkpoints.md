# Phase 1C-A.7：语义冲突审阅与批次检查点

## Run #54 根因

Run #54 使用 `assisted_boundary_review`。Detection Batch 1/2 的 Invocation #93/#94
结构及业务校验通过；Batch 3 的 #95 与 business repair #96 均返回 Schema 合法响应，
但 T0017 同时给出 `boundary_candidate=true`、`goal_relation=refined`、
`action_chain_relation=continuous` 和 `deterministic_reason=null`。确定性规则不允许该组合
自动成为场景边界。旧逻辑把语义争议当成可 Repair 的业务错误，最终令整章失败。

## automatic 与 assisted

- `automatic` 继续调用严格 `validate_candidate_detection()`。模型候选与确定性规则冲突时
  返回 `BUSINESS_VALIDATION_FAILED`，不得生成 Scene 或自动路由。
- `assisted_boundary_review` 先严格校验 Schema、transition 覆盖、顺序、重复和 ID，再调用
  `validate_candidate_detection_for_review()`。语义冲突返回结构化
  `valid_decisions/conflicted_decisions/issues`，不抛 Pipeline 失败。
- JSON、Pydantic Schema、transition 覆盖等结构错误可产生 `structural_repair`；
  语义冲突只统计为 `semantic_review_conflict`，不产生 Repair 请求或费用。

T0017 的稳定记录为：

```text
conflict_code=CANDIDATE_TRUE_WITHOUT_LEGAL_REASON
deterministic_legal=false
deterministic_reason=null
review_priority=high
```

## Checkpoint 生命周期

`BoundaryDetectionBatchCheckpoint` 在每个 v3.5 Detection Batch 结构解析完成后立即提交。
唯一键为 `(run_id, batch_index, prompt_version)`。记录 owned transition ID、上下文段落 ID、
transition 到左右段落 ID 的映射、Invocation、结构响应 hash、valid/conflicted decisions
和 issues；不保存小说正文、凭据或完整 URL。

状态：

- `completed`：结构与语义一致；
- `conflicted_completed`：结构完整，存在人工语义冲突；
- `failed_structural`：JSON/Schema/覆盖错误在允许的结构 Repair 后仍失败；
- `superseded`：保留给显式替代的检查点。

重复写入按唯一键更新，历史 Invocation 不重写。Provider 在部分批次后失败时 Run 进入
`boundary_candidates_partial`；不可恢复结构错误进入 `failed_structural`；首批 Provider
失败进入 `failed_provider`。

## 离线恢复

`recover_boundary_detection_from_invocations(run_id)`：

1. 只读历史 Invocation 并按 detection initial + 后续 attempt 分组；
2. 为每批选择最后一个 Schema 与结构覆盖合法的响应；
3. 使用 assisted 容错校验生成检查点；
4. 不调用 Provider，不创建 Invocation，不增加 Token 或费用；
5. 不修改原 Run 状态。

Run #54 的临时 SQLite 演练恢复：

- Batch 1 → #93，`completed`；
- Batch 2 → #94，`completed`；
- Batch 3 → #96，`conflicted_completed`，T0017 为上述冲突；
- 总 Detection 10 批，已恢复 3 批，未完成 7 批；
- 继续预算估算：预计 8 / 最坏 16 请求，预计 10384 / 最坏 25565 Token，
  预计 0.057632 / 最坏 0.171994 CNY；
- 演练前后 Run #54 均为 `failed`，Invocation=4、Token=9363、费用=0.02889 CNY；
- 临时数据库 `integrity_check=ok`，演练数据库已删除。

## 从已有结果继续

`GET /analysis-runs/{id}/recovery-preflight` 只计算可恢复批次、剩余批次和预算。
`POST /analysis-runs/{id}/recover`（别名 `continue-from-checkpoints`）必须提交新的
`client_request_id`、`confirmed=true` 和新的 `cloud_consent=true`。响应包含
`run_id`、`recovered_from_run_id`、`reused_batch_count`、`remaining_batch_count`、
`reservation_id`、`request_id` 与 `idempotent_replay`。后端创建带
`recovered_from_run_id` 的新 Run，克隆已恢复检查点，只请求未完成 Detection，之后执行
合法候选 Adjudication 并创建 Review Session。原失败 Run 保持不变。

同一 `client_request_id` 返回已有 Run；同一来源已有活动恢复 Run 时也不重复创建。
Reservation 只覆盖剩余 Detection、Adjudication 和结构 Repair。

### Phase 1C-A.7.1 恢复按钮交互

任务详情「从已有结果继续」状态机：`idle → checking → creating_recovery → created|failed`。
禁止静默 return；loading 时禁用并显示文案；成功显示新 Run ID 并定位任务列表。

### Phase 1C-A.7.2 恢复资格与 recover/preflight

恢复路径与普通人工边界任务共用 `ProviderEligibilityService.evaluate_manual_boundary_candidate()`。
HTTP 200 后的业务/Schema 校验失败（如 `BUSINESS_VALIDATION_ERROR`）不再把 Provider 标为
`provider_unhealthy`。资格不要求 `default` / `allow_auto_route`，也不读取旧
`settings.aliyun_enabled` 或 registry `capabilities.enabled` 覆盖云端配置。

`POST /analysis-runs/{id}/recover/preflight` 只返回资格、预算与 `provider_state_version`，
不创建 Run/Invocation，不发模型请求。前端先 preflight 再 `POST .../recover`，并携带
同一 `provider_state_version`；状态变化返回 `PROVIDER_STATE_CHANGED`，资格不足返回带
精确 `blockers` 的 `NO_MANUAL_BOUNDARY_PROVIDER`。

## 合并和审阅

valid 与 conflicted decisions 共同参与 100% transition 覆盖校验。只有确定性合法候选进入
模型 Adjudication；semantic conflict 不由 Adjudication 自动消除，直接进入 Review Session，
默认 `pending/final_boundary=false/high`。

冲突卡展示左右段落、模型候选、枚举、置信度、deterministic reason、conflict code 和批次。
接受冲突必须选择人工原因并可填写理由，最终来源为
`user_accepted_model_conflict`；拒绝不形成边界；保持待审会阻止最终确认。

## 任务详情、安全与审计

任务详情优先显示 `actual_failed_stage`，分开显示 root error 与用户建议，并提供失败
Invocation 的 HTTP/JSON/Schema、错误、批次、transition 和脱敏技术摘要。非预算错误不显示
required/remaining/exceeded。页面显示检查点复用数量，继续前展示剩余预算并防重复点击。

### Phase 1C-A.8 审阅时间线与全部确认

时间线间隙映射到稳定对象（transition_id / decision_id / source / status），点击黄色候选
必须选中对应详情卡并 `scrollIntoView`，不得对 model candidate 空操作。
「全部确认」先校验 pending；未完成时显示中文提示并可定位下一待审项。后端
`BOUNDARY_REVIEW_INCOMPLETE` 返回 `pending_count` 与 `pending_transition_ids`。

迁移只新增恢复关系、检查点表和 Decision 冲突字段；幂等执行，不删除或重写历史数据。
Plus `default=false`、`allow_auto_route=false` 保持不变。自动测试和 E2E 使用 Fake Provider，
不设置 `STORYLENS_RUN_ALIYUN_TESTS=1`。
