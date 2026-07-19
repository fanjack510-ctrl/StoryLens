# 12｜阿里云百炼千问 Provider

## 目标与定位

本地 27B 仅保留手动短任务，本地 14B 可作辅助模型但未通过场景边界质量门槛。Phase 1B.4 引入阿里云百炼北京地域 OpenAI 兼容接口，候选角色为 Plus 自动分析、Max 人工复核、Flash JSON/Schema 修复。三者均复用通用 Model Gateway，领域流水线不依赖阿里云 SDK 或具体模型名。

## 配置与隐私

配置只从 `STORYLENS_ALIYUN_*` 环境变量读取。Workspace ID 可用于派生 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`，也可由用户显式提供 Base URL。API Key、Authorization Header、本机 Workspace ID 和完整云端正文不进入源码包。

云端 AnalysisRun 必须使用 `execution_mode=cloud|hybrid` 且 `cloud_consent=true`。本地模式不会自动上云。Run 保存同意时间、Provider、模型和内容哈希；`STORYLENS_CLOUD_RAW_LOGGING=false` 时 Invocation 只保存段落 ID、字符数、内容哈希、Token 和请求审计，不保存完整请求正文或原始响应。

## 结构化输出与审计

结构化任务使用 Prompt v2、`response_format={"type":"json_object"}` 和 `enable_thinking=false`，随后仍执行 JSON 提取、Pydantic、业务规则和 Evidence 范围校验。网络错误在原 Provider 重试；JSON/Schema 错误可由 Flash 修复；Evidence/业务错误仍由 Plus 修复；Max 不被自动调用。

Invocation 支持云厂商、地域、是否上传、输入/输出/总/缓存 Token、request ID、响应模型、内容与 Schema 哈希、thinking、结构模式和可选成本估算。价格来自本机版本化配置；价格未知时费用保持 null。

## 当前验证状态

本轮工作区没有有效的 `STORYLENS_ALIYUN_API_KEY`、Workspace ID 或 Base URL，旧版百炼配置也处于 disabled 且没有 Key。因此没有发出收费请求，未产生云端 Token 或费用。Plus/Max/Flash 最小 JSON、八组真实校准和完整 Run 均未实测；Plus 保持 `default=false`，暂不进入 Phase 1C。
# Phase 2A 配置中心补充

桌面端可保存阿里云百炼的非敏感配置；API Key 只写入操作系统 keyring，SQLite 仅保存凭据引用和状态。保存配置不会发起云端调用。单 Provider 启停以 `ProviderConfiguration.enabled` 为准（`STORYLENS_ALIYUN_ENABLED` 不再作为单 Provider 健康状态）。「传输诊断」只检查 DNS/TCP/TLS 等，不调用模型；「真实连接测试」要求显式费用确认。全局云端开关和每次 AnalysisRun 的 `cloud_consent` 是两个独立安全门，二者均不能被 UI 绕过。详见 `docs/24_phase_1ca5_provider_transport.md`。
