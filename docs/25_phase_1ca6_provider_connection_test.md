# Phase 1C-A.6：真实连接测试确认与审计

## 问题与根因

旧版“真实连接测试”并不执行 JSON 生成。前端调用
`POST /api/v1/model-providers/{provider_name}/test`，后端仅执行
`provider.health()`，即访问 OpenAI 兼容接口的 `/models`。因此返回值只有
`status=healthy`，不会产生 ModelInvocation、Token、费用或模型响应字段。

前端使用浏览器原生 `confirm()`，没有可审计的确认状态、预算预览、loading
状态或结构化结果。`testMsg` 与传输诊断结果虽是两个变量，但渲染在同一块内容中，
视觉上会把“真实连接测试结果：healthy”与下方 DNS/TCP/TLS 误认为同一结果。
此外，按钮曾被页面级 `blocked_reasons` 直接禁用，用户无法打开说明并看到门禁原因。

## 两条独立流程

### 传输诊断

- 接口：`POST /api/v1/model-providers/{name}/transport-diagnostic`
- 只检查配置、DNS、TCP、TLS、代理、CA 与 endpoint 形态
- 不调用 `/chat/completions`
- 不创建 ModelInvocation
- 不消耗 Token，不产生模型费用

### 真实连接测试

1. 前端立即打开“执行真实连接测试”确认框。
2. `POST /api/v1/model-providers/{name}/test/preflight` 读取Provider、价格和剩余预算。
3. 用户明确点击“确认并测试”。
4. 前端再次执行零生成 preflight，防止确认期间预算变化。
5. `POST /api/v1/model-providers/{name}/test`，请求体：

```json
{
  "confirmed": true,
  "test_type": "minimal_json",
  "max_output_tokens": 32
}
```

6. 后端只调用当前选中的 Provider 和配置模型一次。
7. 请求只含原创合成指令，要求返回 `{"status":"ok"}`。
8. `temperature=0`、`thinking=false`、`response_format=json_object`。
9. 不执行 repair、自动重试或模型切换。
10. 原始响应正文不落库；仅保存 Pydantic 校验后的最小结构和审计字段。

## 状态机

传输诊断：

`idle → running → succeeded | failed`

真实连接测试：

`idle → awaiting_confirmation → checking_budget → running → succeeded | failed`

两套结果分别渲染；真实测试结果包含 HTTP、配置模型、响应模型、JSON/Schema、
Token、耗时、Invocation、脱敏 request ID、费用和价格版本。

## 预算与审计

- 未确认：HTTP 422，不调用 Provider，不写 Invocation。
- 门禁失败：写一条拒绝的 RequestGateDecision，不调用 Provider。
- 门禁通过：写一条允许的 RequestGateDecision。
- 真实测试本身不创建 CloudBudgetReservation；一次请求在发送后立即由
  ModelInvocation 纳入每日用量。
- 成功和 Provider 失败都只创建一条 ModelInvocation。
- Connection Test 使用独立的 `connection_test` task/invocation kind。

## 环境变量

正式 UI 的授权来自用户二次确认、云端总开关、Provider/Credential 和预算门禁，
不依赖 `STORYLENS_RUN_ALIYUN_TESTS=1`。

命令行真实阿里云探针仍必须由 `STORYLENS_RUN_ALIYUN_TESTS=1` 显式保护。自动化
测试只使用 Fake Provider。

## 安全边界

- 不读取 Book、Chapter 或 Paragraph。
- 不发送小说、章节、段落或用户文件。
- 不调用 Max 或 Flash。
- 不保存 API Key、Authorization、Workspace ID、完整 Base URL 或原始响应。
- 返回给 UI 的 Provider request ID 使用哈希短标识。
- `default` 与 `allow_auto_route` 不因测试而修改。
