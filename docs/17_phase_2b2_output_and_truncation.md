# Phase 2B.2 云端输出配额与截断恢复

## 根因

`structured_output.generate_validated` 曾把全部结构任务的 `max_output_tokens` 绑定到
`Settings.local_llama_max_output_tokens`。该本地安全档默认值为 128，云端预算设置中的
`cloud_max_output_tokens_per_request=2000` 仅参与预算门禁，没有进入 ModelRequest。
OpenAICompatibleProvider 最终将 128 写入兼容接口 payload 的 `max_tokens`，首次请求和
repair 因而都受到同一错误上限约束。

## 修复

`CloudTaskOutputPolicy` 统一维护任务上限：连接测试 64、最小 JSON 128、Boundary 768、
Scene Analysis 1600、JSON/Schema repair 1200、业务/Evidence repair 1600。云端任务在发送前
与用户硬上限比较；硬上限不足时返回 `CLOUD_OUTPUT_LIMIT_TOO_LOW`。Invocation 记录请求和
实际输出 Token、Provider 参数名及 finish reason，不记录正文或凭据。

`finish_reason=length|max_tokens` 和明显未闭合 JSON 统一分类为 `OUTPUT_TRUNCATED`。该错误
不调用 Flash，而由同一主 Provider 从头完整生成一次，不续写、不拼接。完整 JSON 的语法或
Schema 错误仍可交给 Flash；Evidence 和业务错误仍由主 Provider 修复。单任务最多两次调用。

原创验收 fixture 使用 fixture 名称、版本和规范化正文计算稳定 SHA-256；相同版本复用 Book，
版本变化创建新 Book，每次复验仍创建独立 AnalysisRun。数据库唯一约束保持不变。

Prompt v3 保留，v3.1 增加核心目标持续行动链、正文注入文本和物件触发目标变化的通用判据，
同时要求 Scene Analysis 首次完整返回全部契约字段。
