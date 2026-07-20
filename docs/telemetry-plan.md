# 匿名使用统计计划（StoryLens Desktop）

## 为什么收集

StoryLens 是本地优先工具。可选匿名统计用于了解：

- 大致安装与活跃规模（无账号体系时）
- 版本与平台分布，便于 prioritise 兼容性
- 哪些功能被实际使用，避免凭猜测排期

**默认不发送任何数据。** 只有用户在设置中明确开启后才启用。

## 收集什么

仅在用户同意（`ENABLED`）后，通过白名单事件发送：

| 事件 | 用途 |
|------|------|
| `app_launched` | 会话级启动计数 |
| `analysis_started` / `analysis_completed` | 分析流程漏斗（桶化维度，无正文） |
| `feature_used` | 功能键命中 |
| `update_installed` | 版本升级跨度 |

允许属性：`app_version`、`os_family`、`locale`、`feature_key`、`execution_mode`、`status`、`duration_bucket`、`scene_count_bucket`、`from_version`、`to_version`。

匿名 `install_id`：首次需要时在用户配置区生成随机 UUID，可在设置中重置。

## 不收集什么

禁止出现在事件中的字段包括但不限于：

- 书名、章节、段落、任何小说文本
- 文件路径、API Key、提示词、原始错误详情
- 用户名、机器名、MAC、磁盘序列号、精确设备指纹

传输层不启用录屏、DOM 自动捕获或完整错误堆栈上报。

## 同意与关闭

| 状态 | 行为 |
|------|------|
| `UNKNOWN`（默认） | 不发送 |
| `ENABLED` | 发送白名单事件 |
| `DISABLED` | 不发送；关闭后立即生效 |

用户可在「匿名使用统计」设置卡片中开关，并重置 `install_id`。

## 数据保留建议

- 聚合指标保留 12–24 个月即可满足产品决策；更细粒度事件可更短。
- 重置 `install_id` 后，新旧 ID 不应在分析侧强行关联。
- 若未来提供数据导出/删除请求通道，以安装 ID 为最小粒度。

## PostHog 与自建切换边界

当前实现：

- `TelemetryTransport` 抽象 + `NoopTelemetryTransport` + `HttpTelemetryTransport`
- 构建时环境变量：`VITE_TELEMETRY_ENDPOINT`、`VITE_TELEMETRY_PROJECT_KEY`
- 未配置 endpoint/key 时恒为 Noop，**不影响本地分析**
- HTTP 体兼容 PostHog `/capture/` 最小字段；**不在源码中硬编码私有管理密钥**

切换自建服务时：只需替换 endpoint 与 ingest 契约适配层，保留 schema 白名单与同意门禁；业务代码继续调用 `TelemetryClient.track`。

## 尚未上线（本阶段）

- **未** 修改 `SettingsPage.tsx`：设置卡片组件已就绪，尚未挂入主导航。
- **未** 修改首次启动向导：不会在 onboarding 中弹同意框。
- **未** 在应用启动/analysis 路径自动打点（仅 foundation + 测试）。
- **未** 在 CI/Release 流水线注入生产 PostHog 项目（需发布流程单独配置 env）。
- **未** 后端 API 侧统计；全部为桌面端 opt-in 出站事件。

详见 `apps/desktop/src/services/telemetry/` 与 `apps/desktop/src/components/settings/TelemetrySettingsCard.tsx`。
