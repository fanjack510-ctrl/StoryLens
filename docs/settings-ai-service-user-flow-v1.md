# Settings & AI Service User Flow v1

**Phase:** 1D-C1-UI-01  
**Scope:** CHANGEABLE_UI_SHELL only（前端壳层）  
**Constraint:** 不调用真实模型；不创建 AnalysisRun；不解冻 Reader Journey UI Final Baseline v2.7

## 两层界面

| 模式 | 入口 | 可见内容 |
|------|------|----------|
| 普通用户 | 主导航：我的书库 / 设置 | 通用 · AI服务 · 预算与隐私 |
| 开发者 | 侧栏底部「开发者模式」开关（默认关） | 额外显示高级设置；开发路由：工作台 / 任务 / 案例 / 模型与API |

系统状态、模型与API **不再作为普通导航独立入口**，工程信息并入设置「高级设置」。

## 普通用户：AI 服务配置

默认服务展示名：**阿里云百炼** · 模型：**qwen3.7-plus**（内部仍绑定 `aliyun_qwen_plus`，主界面不展示 provider_id）。

1. 打开 **设置 → AI服务**
2. 点击 **配置**
3. 步骤1：选择 AI 服务（展示名）
4. 步骤2：输入 API Key
5. 步骤3：保存并测试连接（仅传输诊断，**零 Token**）
6. 步骤4：成功或可理解错误；「查看诊断详情」可看原始码

状态卡展示：服务名、模型、连接文案、API Key 是否已配置、今日费用。  
操作：测试连接 · 配置/重新配置 · 断开连接。

## 状态文案映射（前端 view model）

| 内部码 / 条件 | 用户文案 |
|---------------|----------|
| provider_not_configured | 尚未配置AI服务 |
| credential_missing | 尚未填写API Key |
| provider_disabled | 云端AI尚未开启 |
| provider_disconnected | 尚未连接AI服务 |
| DNS failed | 无法连接云端服务，请检查网络或代理设置 |
| 401/403 | API Key无效或没有模型访问权限 |
| healthy | 已连接，可以开始分析 |
| awaiting_provider_recovery | 云端服务暂时波动，系统正在自动恢复 |

主界面不直接展示：`unhealthy`、`configured_readiness`、`provider_disabled`、`provider_not_configured`、`provider_disconnected`（仅诊断详情）。

## 预算与隐私

普通用户只见：

- 启用云端AI（合并原「允许云端模型连接 / 云端总开关」）
- 每日预算上限 / 今日已使用 / 剩余预算
- 每次收费测试需要确认
- 云端数据发送说明

Token 闸门、AnalysisRun 请求上限、价格未知停止、价格版本 → **高级设置**。后端预算语义不变。

## 开始分析弹窗

普通模式：

- 分析范围
- 当前 AI 服务 · 模型 · 连接状态
- 云端正文确认
- 创建任务（未连接时禁用，并提供「前往设置」）

无 Provider 下拉。开发者模式恢复完整 Provider / 执行模式 / Provider 诊断。

## 实现文件（前端）

- `stores/developerModeStore.ts`
- `services/aiServiceViewModel.ts`
- `pages/SettingsPage.tsx` + `components/settings/*`
- `components/layout/DevelopmentNavigationGroup.tsx`
- `components/analysis/StartAnalysisDialog.tsx`（按开发者模式分支展示）
- `styles/global.css`

## 截图

`audits/single-chapter-pipeline/ui-changes/screenshots/`

1. `01-settings-general.png`
2. `02-settings-ai-disconnected.png`
3. `03-settings-ai-connected.png`
4. `04-settings-budget-privacy.png`
5. `05-settings-advanced-developer.png`
6. `06-start-analysis-connected.png`
7. `07-start-analysis-disconnected.png`
