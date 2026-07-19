# 09 — Known Issues

基于代码审计、前端缺口说明、以及 `audits/v1.0/v1.0-defect-register.json` / readiness report。  
**工程缺陷寄存器当前 open P0/P1 = 0**；下列为基线期仍应跟踪的风险与体验债（含已关闭但待 Human UAT 确认项）。

## UI 问题

| ID | 问题 | 严重度 |
|----|------|--------|
| UI-01 | 书库文件类型筛选、排序控件未接线 | 低 |
| UI-02 | `BookWorkspacePage` 分析侧栏仍有「规划中」占位能力文案 | 低 |
| UI-03 | Metric Selector 曾遮挡旅程内容（DEFECT-UAT-009）— 代码侧 v4.2 已修，待最终人审 | 中（验证） |
| UI-04 | CasesPage / 多 Provider 品牌入口为灰置或占位，易被误认为半成品 | 低 |

## UX 问题

| ID | 问题 | 严重度 |
|----|------|--------|
| UX-01 | 无跨会话阅读书签（章节/滚动） | 中 |
| UX-02 | URL `chapter` 与嵌入阅读器本地状态可能不同步 | 中 |
| UX-03 | `/tasks?run_id=` 深链不被 TasksPage 消费 | 低（开发模式） |
| UX-04 | 任务中心 / Providers 藏在开发者模式，普通用户故障排查路径偏设置页 | 低 |
| UX-05 | 预算不足创建任务曾出现「灰按钮无解释」（DEFECT-V1-001）— 已修，待 UAT | 中（验证） |
| UX-06 | 临时提额与日限额语义复杂，需依赖文案正确传达 | 中 |

## 性能问题

| ID | 问题 | 严重度 |
|----|------|--------|
| PERF-01 | 分析进度前端短间隔轮询（约 2s），长跑占连接与渲染 | 低–中 |
| PERF-02 | 大章段落分页拉取；旅程同步模式下文本+SVG 同屏，低配机可能卡顿 | 中 |
| PERF-03 | `model_invocations` 存 raw 响应，DB 体积随云端调用增长快 | 中 |
| PERF-04 | 全流水线在同进程 `BackgroundTasks`，API 与重任务争用 | 中 |

## API / 架构问题

| ID | 问题 | 严重度 |
|----|------|--------|
| API-01 | `POST .../recover` 双路由注册，统一恢复中心覆盖旧 checkpoint handler | 低（已约定） |
| API-02 | 无 Alembic 修订树，schema 靠代码内 ALTER，协作/升级可追溯性弱 | 中 |
| API-03 | 无独立 worker；进程中断依赖 startup `mark_interrupted_runs_failed` | 中 |
| API-04 | 历史文档 `docs/05_api_contract.md` 含过时路径，易误导 | 低 |
| API-05 | `AGENTS.md` 阶段边界相对 V1.0 RC 过时 | 低（文档债） |

## AI / 成本问题

| ID | 问题 | 严重度 |
|----|------|--------|
| AI-01 | 单章全链路请求数偏高（边界分批 + 裁决 + 每场景分析 + 旅程）；日限额易触顶 | 高 |
| AI-02 | 最坏情况预估偏保守，可能阻止创建（需临时额度） | 中 |
| AI-03 | 真实费用完全取决于用户阿里云账单；产品侧只能估算 | 中 |
| AI-04 | 普通模式锁定 Qwen Plus；Max/Flash 仅开发/手动，误配成本风险靠 broker 门禁 | 中 |
| AI-05 | Prompt/契约多版本并存，运维需严格跟随 run 冻结版本 | 中 |

## 开源 / 发布门禁（非代码缺陷）

| ID | 问题 | 严重度 |
|----|------|--------|
| REL-01 | 根目录无 LICENSE | 高（法务） |
| REL-02 | Human UAT / Clean Install 未最终封板 | 高（发布） |
| REL-03 | 本机曾无 Git 仓库，历史可追溯性依赖新建基线 tag | 中 |
| REL-04 | macOS/Linux 未正式认证 | 中 |

## 已关闭缺陷（待人审确认）

详见 `audits/v1.0/v1.0-defect-register.json`：DEFECT-V1-001/002、UAT-001–007、UAT-009 等均为 CLOSED，`human_verification` 多为 PENDING。
