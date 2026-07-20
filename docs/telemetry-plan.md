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

## 尚未接线（本阶段）

- **`feature_used`**：功能键命中尚未在 UI 路径挂载可靠触发点；schema 与 `TelemetryClient` 已就绪。
- **`update_installed`**：更新安装成功回调尚未与遥测挂钩；检查更新失败不影响分析。
- **生产 ingest**：Release 流水线注入 `VITE_TELEMETRY_*` 仍由发布流程单独配置；未配置时使用 Noop。

## 已接线（v0.1.0 Preview 集成）

- 设置「隐私与更新」页：`TelemetrySettingsCard`（opt-in 开关、不收集说明、安装 ID 重置）。
- 设置「授权与会员」页：`LicenseSettingsCard`（免费版 / 即将开放；DEV Mock 仅开发模式）。
- 首次启动向导第三步：可选匿名统计（默认不勾选；完成时 ENABLED/DISABLED；跳过保持 UNKNOWN）。
- **`app_launched`**：`DesktopBootstrap` 本地 API 就绪后每会话一次（sessionStorage 防 HMR 重复）。
- **`analysis_started`**：`StartAnalysisDialog` 任务创建成功后。
- **`analysis_completed`**：任务进入终态（`useCurrentPageAnalysisProgress` / 任务列表轮询），含桶化 `duration_bucket` / `scene_count_bucket`（有数据时）。

详见 `apps/desktop/src/services/telemetry/` 与设置卡片组件。
