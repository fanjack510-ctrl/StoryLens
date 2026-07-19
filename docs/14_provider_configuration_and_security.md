# Provider 配置与凭据安全

## 数据分层

`provider_configurations` 只保存显示名、区域、Workspace ID、Base URL、模型路由、超时、重试次数、启用状态和凭据引用。API Key 不进入 SQLite、源码、日志、响应或测试样本。桌面设置保存于 `application_settings`。

凭据通过 `CredentialStore` 抽象访问。生产默认实现使用操作系统 keyring，自动测试使用内存 Fake store。数据库仅保存 `keyring:<provider>` 引用；配置读取 API 只返回 `configured`、`missing` 或 `unknown`。

## 安全状态机

- `disabled`：Provider 未启用。
- `unconfigured`：已启用但无凭据。
- `connected`：配置存在、凭据存在且未断开。
- `disconnected`：用户主动断开，配置和凭据可保留。

删除凭据会清除 keyring 项、数据库引用并进入 disconnected。保存配置不会自动发送测试请求。真实连接测试先执行零生成预算 preflight，再要求用户在 UI 二次确认；正式请求显式提供 `confirmed=true`，并只允许一次最多 32 Token 的原创最小 JSON 请求。兼容字段 `confirm_paid_request=true` 仍被接受，但新 UI 不再使用。详见 `docs/25_phase_1ca6_provider_connection_test.md`。

## 云端内容同意

全局云端开关默认关闭。创建云端 AnalysisRun 仍必须遵循既有 Phase 1B.4 的逐次 `cloud_consent` 校验；桌面端同时展示“正文将发送至云端”的清晰提示。关闭全局开关不删除配置或凭据，但 UI 不应将云端 Provider 当作自动路线。

## API

- `GET|PUT /api/v1/settings/cloud`
- `GET|PUT /api/v1/settings/desktop`
- `GET|PUT /api/v1/model-providers/{name}/configuration`
- `POST /api/v1/model-providers/{name}/connect|disconnect|enable|disable`
- `POST /api/v1/model-providers/{name}/validate-configuration`
- `POST /api/v1/model-providers/{name}/test`
- `DELETE /api/v1/model-providers/{name}/credentials`

Provider 配置中心不在业务代码中增加特定模型调用分支；实际推理仍统一经过 ModelGateway。API Key 只在 CredentialStore 边界出现。
