# 24｜Phase 1C-A.5 Provider 传输诊断与错误分类

## 1. Run #52 误分类（冻结结论）

Run #52 在首个 Boundary Candidate Detection 批次发生 Provider 传输失败（2 次 `http_request_sent=true`，无 HTTP status / Token / 响应体）。  
`generate_validated` 将空的 `last_error` 包装为 `StructuredOutputError("")`，`classify_pipeline_error` 默认落入 `BUSINESS_VALIDATION_FAILED`，并把 `retryable` 标为 false。  
**历史 Run #52 不做数据改写**；任务中心对同类历史记录显示“可能由旧版本错误分类产生”。

## 2. Provider 异常体系

`ProviderRequestError` 携带：

- `error_code` / `message`（永不空） / `exception_type` / `transport_kind`
- `retryable` / `http_status` / `timeout_kind` / `safe_details`
- 保留 `__cause__`

`transport_kind` 覆盖 DNS、连接/读写超时、TLS、代理、协议、HTTP 等。  
错误文案脱敏：禁止完整 URL、API Key、Authorization、Workspace ID、正文。

## 3. 传输诊断 vs 真实连接测试

| | 传输诊断 | 真实连接测试 |
|---|---|---|
| 接口 | `POST .../transport-diagnostic` | `POST .../test` |
| 模型调用 | 否 | 是（需确认） |
| Token/费用 | 0 | 可能少量 |
| Invocation | 不创建 | 可能创建 |
| 检查项 | 配置 / DNS / TCP / TLS / 代理 / CA / Endpoint 形态 | 单次原创最小 `{"status":"ok"}` JSON 生成 |

推荐排障：传输诊断通过 → 用户主动真实连接测试 → 再创建章节任务。

Phase 1C-A.6 已将旧 `/models` 健康探测升级为收费确认、预算 preflight、单次
`/chat/completions` 最小 JSON 测试和 ModelInvocation 审计。详见
`docs/25_phase_1ca6_provider_connection_test.md`。

## 4. Retry 语义

默认可重试：连接超时、连接错误、读超时、远端断开、协议错误、HTTP 429/5xx。  
默认不可重试：认证失败、无效 URL、Provider 停用、云端总开关关闭、证书校验失败。

## 5. enabled 状态统一

- **单 Provider 启停事实源**：`ProviderConfiguration.enabled`
- **云端总开关**：`ApplicationSetting.cloud_enabled`（`settings.aliyun_enabled` 仅作总开关缺失时的废弃回退）
- `health()` 与 `generate()` 使用同一 `provider.enabled`；disabled 时不得发包

## 6. 安全脱敏

日志与 API 允许：Provider/模型名、异常类型、`transport_kind`、HTTP status、latency、host hash、脱敏 path。  
禁止：API Key、完整 URL、Workspace ID、小说正文、完整模型响应。

## 7. 用户排障步骤

1. 打开「模型与API」→ 选中 `aliyun_qwen_plus`
2. 确认云端总开关与 Provider 已启用
3. 运行「传输诊断」（零 Token）
4. 若 DNS/TCP/TLS 失败，按提示修复网络/代理/证书/Base URL
5. 诊断通过后，再手动执行「真实连接测试」
6. 成功后再创建 assisted_boundary_review 任务
