# StoryLens 普通用户设置设计

本文档描述 V1.0 设置界面简化方案：将偏开发者/工程化的配置收敛为普通读者与写作者可理解的路径，同时保留高级能力与开发者入口。

## 当前配置项（改造前）

| 配置项 | 入口 | 说明 |
| --- | --- | --- |
| 主题 / 字号 / 行距 / Demo 模式 | 设置 · 通用 | 桌面 `DemoSettings` |
| 检查更新 | 设置 · 通用 | Tauri updater |
| AI 服务状态 / 四步向导 | 设置 · AI 服务 | Provider `aliyun_qwen_plus`、传输诊断 |
| 启用云端 AI / 每日预算 / 正文说明 | 设置 · 预算与隐私 | `cloud-budget`、`cloud` |
| Provider 列表 / Aliyun 工程表单 / 路由 / 高级预算 / 本地模型 / 诊断 JSON | 设置 · 高级（需开发者模式） | 模型网关与系统诊断 |
| 模型与 API 全页 | 导航 · 开发者模式 | `ProvidersPage` |
| 任务 / 案例 / 工作台 | 导航 · 开发者模式 | 工程路由 |
| 书库横幅 | 书库 | Qwen API Key 深链 |

## 分类

### 普通用户必须看到

- AI 服务：阿里云百炼（推荐）、API Key、分析模式（快速 / 均衡 / 高质量）、测试连接、保存
- 使用费用：单章预计费用、本月（日）用量、费用上限、费用说明
- 数据与存储：数据目录、打开目录（复制路径）、备份/恢复（真实未实现状态）、清理缓存（未实现）、日志占用（占位）
- 隐私与更新：自动检查更新说明、匿名统计占位、隐私说明、版本、检查更新
- 授权与会员：免费版、VIP 占位、激活码插槽
- 外观：主题、字号、行距

### 软件自动处理

- Endpoint / Base URL（百炼兼容模式）
- 默认 Model ID（由分析模式预设映射）
- Temperature / Context Window（后端与 Provider 默认）
- Provider Protocol、Prompt 版本（分析流水线）
- 云端 Master 开关（保存 AI 配置时自动启用，普通模式不暴露独立开关）
- Reservation / staged budget / run-scoped 授权（后端预算引擎）

### 高级用户可见（「显示高级设置」开启）

- 自定义 Provider、Endpoint、Model ID、Temperature、Max Tokens、Context Window
- 本地模型启停
- 云端预算明细（Token/请求闸门、定价 JSON）
- Prompt 版本只读说明
- API 连接信息、传输诊断
- 恢复与诊断、日志 JSON
- 分析模式「自定义（CUSTOM）」
- 开发者模式开关（同时恢复导航中的工程路由）

### 仅开发者可见（开发者模式 + 高级设置）

- Providers / Tasks / Cases / Workspace / Prompt 管理（ProvidersPage 内）
- 模型网关路由预览
- Demo 模式开关

### 重复入口（已收敛）

- ~~通用 + 预算与隐私 中的更新检查~~ → 合并到「隐私与更新」
- ~~AI 向导中的每日预算~~ → 合并到「使用费用」
- ~~书库横幅与设置 AI 重复文案~~ → 首次向导 + 跳过后书库入口

## 新设置结构

1. **AI 服务**
2. **使用费用**
3. **数据与存储**
4. **隐私与更新**
5. **授权与会员**
6. **外观**
7. **高级设置**（默认隐藏，由「显示高级设置」开关控制）

## 分析模式预设

集中定义于 `apps/desktop/src/services/analysisModePresets.ts`：

| ID | 显示名 | Provider | 主模型 | 用途 |
| --- | --- | --- | --- | --- |
| FAST | 快速 | aliyun_qwen_plus | qwen3.6-flash | 较低 Token 上限与批次 |
| BALANCED | 均衡（推荐） | aliyun_qwen_plus | qwen3.7-plus | 默认 |
| QUALITY | 高质量 | aliyun_qwen_plus | qwen3.7-max | 更高输出与超时 |
| CUSTOM | 自定义 | — | 高级设置手工配置 | 仅高级 |

## 首次启动（最多三步）

1. 欢迎：产品定位说明
2. 连接 AI：百炼 + Key + 均衡 + 测试（可跳过 / 其他服务 / 本地模型 → 高级或稍后）
3. 开始使用：导入第一本小说或进入空书库

完成或跳过后写入本地标记，不再重复；跳过后书库保留配置入口。
