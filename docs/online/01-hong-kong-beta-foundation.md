# StoryLens Online：香港 Beta 状态与路线图

## 当前结论

Phase 2A 在其冻结范围内已 **100%** 完成。Phase 2B1 的“真实 AI 最小纵向链路”
现已通过香港生产白名单验收，`CHG-20260830-005` 已 `verified`。本次状态记录依据
用户于 2026-09-03 提供的香港部署操作者验收事实；记录更新不代表重新远程执行验收。

这仍**不是正式公开 Beta**。真实全书分析、充值、钱包、正式计费和公开 onboarding
均未开放。真实模型验证结束后，生产 `PHASE2B1_ENABLED=false`，白名单为空。

当前线上基线：

| 项目 | 状态 |
|------|------|
| 代码提交 | `4ae7f663999caad09f5f57c7cff3a2f82b81f924` |
| 正式目录 | `/opt/storylens/releases/4ae7f663` |
| 当前软链接 | `/opt/storylens/current` 已指向正式目录 |
| 网站根地址 | `https://app.dstorylens.com/`，HTTP 200 |
| `health/live` | `status=ok`、`runtime=hong_kong_beta` |
| API / Web / PocketBase / PostgreSQL / Redis | healthy |
| Worker | 正常运行 |
| `pocketbase-init` | 正常 `Exited (0)` |
| 生产日志安全 | `PRODUCTION_LOG_SAFETY=OK` |
| 真实模型功能开关 | `PHASE2B1_ENABLED=false` |
| 真实模型白名单 | `PHASE2B1_ALLOWLISTED_USER_IDS=`（空） |
| 根目录版本 | `VERSION=1.3.6`，未因 Online Beta 修改 |
| Git 发布动作 | 未推送、未发布、未创建标签 |

当前回滚镜像、切换前数据库/PocketBase/uploads/Redis 备份及验收日志均保留。
本次部署和验收的规范化记录位于
[`CHG-20260830-005`](../../release/changes/CHG-20260830-005.json)。
此前 Phase 2A 在 `ad896056` 上的验收、隔离资源清理及部署历史保留在
[`CHG-20260830-004`](../../release/changes/CHG-20260830-004.json)，不以本轮状态覆盖。

## Phase 2A 已完成范围

本阶段建立独立的线上边界，不修改 StoryLens 1.3.6 桌面安装版：

- 独立 `apps/online_api`、`apps/online_web` 和 `infra/online`；
- PocketBase 注册、登录及由 FastAPI BFF 管理的安全会话；
- TXT 上传、用户所有权隔离、Redis pending/processing 队列；
- PostgreSQL 原子任务领取、任务租约、恢复和重复消费幂等；
- 确定性的 `phase2a_smoke` 统计结果与页面展示；
- PostgreSQL 七张 `online_` 表的幂等启动初始化；
- Worker 空队列轮询、Redis 短暂故障退避和 processing 恢复；
- PocketBase migration 与内部超级管理员的启动前安全预置；
- Caddy 同域入口，公网仅开放 80/443；
- PostgreSQL、Redis、PocketBase 和上传文件的持久卷及备份/回滚边界。

真实香港环境已经验证：

1. PocketBase 空卷首次启动成功，既有 migration 与 `users` auth collection 正常；
2. 重复初始化不会创建重复超级管理员或破坏已有数据；
3. Secret 缺失或初始化失败时正式 PocketBase 不启动；
4. 只有 `pocketbase-init` 挂载管理员 Secret；
5. PocketBase 8090、管理界面和内部 API 不暴露公网；
6. 正式日志没有安装地址、JWT 或管理员密码模式；
7. Worker 在真实 Redis 环境保持运行，空队列不再触发重启循环。

## 保持不变的隔离约束

1. 不修改 `apps/desktop` 和本地 `apps/api` 的运行路径。
2. 不读取或复用桌面版 Windows/macOS Provider 凭据。
3. 在线配置拒绝 SQLite，在线数据表统一使用 `online_` 前缀。
4. 浏览器只访问 FastAPI BFF，不接触 PocketBase 管理员凭据。
5. 正式 Secret 不进入 Git、镜像层、Compose 持久配置、日志或前端。
6. 在线组件部署与桌面正式版本发布解耦；Online Beta 不进入冻结的桌面
   `release/unreleased.json` 发布池。

## Phase 2B1 真实 AI 最小纵向链路（已 verified）

`CHG-20260830-005` 在 Phase 2A 链路上增加了一个默认关闭、白名单为空的内部真实分析
门禁。该实现已部署到上述 `4ae7f663` 生产基线，并通过单一测试账户的受控真实请求验收：

- 新 pipeline 固定为 `phase2b1_txt_evidence_summary`；`phase2a_smoke` 仍是默认值；
- 受控 AI 分析固定走 Worker-only Provider 网关；浏览器和 API 不能选择或覆盖
  Provider、URL、模型、thinking、定价或汇率；
- API 创建任务和 Worker 执行前分别检查全局开关及用户 ID 白名单；
- Worker 为 TXT 生成确定性 `P000001` 格式段落 ID，模型的概述和每条发现都必须引用
  输入中真实存在的 ID；结构先由 Pydantic 校验，再校验证据集合；
- 每次 HTTP 尝试前创建独立账本行，记录原始 Provider usage、请求 ID、状态、时间、
  冻结价格快照和内部人民币成本；任务重试次数与 Provider attempt 编号相互独立；
- `started` 崩溃遗留、响应读取超时和响应丢失按未知结果关闭，禁止自动重试；明确连接前
  失败和 429 才按规则重试，无效结构在 usage 完整时最多重试一次；
- Provider Secret 是只挂载到 `online-worker` 的文件型 Docker Secret。API、Web、
  Gateway、PocketBase 和初始化容器都不能获得；
- 钱包、预留、交易、充值和爱发电仍不参与本阶段。`customer_charge_cny=0`、
  `billing_status=not_billable`、公开 `charged_cny=0`。

冻结成本公式使用 `Decimal`，每次尝试分别计算后再按任务汇总：

```text
provider_cost_usd =
  (cache miss token × miss USD 单价 + cache hit token × hit USD 单价
   + output token × output USD 单价) / 1,000,000
provider_cost_cny = provider_cost_usd × 6.7811
```

价格版本为 `deepseek-v4-flash@2026-08-30`，汇率版本为
`safe-usdcny-central-parity-2026-08-28`。每次尝试按 `request_sent_at` 的 UTC 峰谷时段
冻结三项美元单价；单任务最多两次 Provider 调用，发送前按本次最坏成本叠加既有实际
成本检查 `0.50 CNY` 上限。

## Phase 2B1 香港生产验收记录

### 迁移并发与数据保留

在香港隔离 Compose project 和隔离数据卷中完成两组 API/Worker 同时首次启动：

| 快照 | 结果 | 进程与数据证据 |
|------|------|----------------|
| Phase 2A 原始 14 列账本 | 升级为 38 列 | API/Worker 均 `restart=0`；`analysis_jobs=1`、`uploads=1`、`usage_rows=0` 保留；无 `DuplicateColumn`、`ProgrammingError`、`Traceback` 或 `schema initialization failed` |
| 合法 20 列部分迁移 | 补齐为 38 列 | API/Worker 均 `restart=0`；原数据未丢失；`uq_online_usage_run_attempt` 正确绑定 `(analysis_run_id, attempt_no)`；`PARTIAL_CONCURRENT_MIGRATION_LOG=OK` |

实际初始化边界为 `engine.begin → pg_advisory_xact_lock → metadata.create_all →
Phase 2B1 migration → commit`，锁、检查和 DDL 始终共享同一 Connection 和同一事务。
此前 DuplicateColumn 失败及回滚记录继续保留，不能把重启后的偶然成功当作首次验收通过。

### Worker Secret 与网络边界

- 原始 DeepSeek Secret 保持 `root:root 600`，只有 `online-worker` 挂载；
  API、Web、PocketBase、Gateway 均无此挂载。
- 开启时 tmpfs 副本权限为 `400`、owner 为 `10001:10001`；Worker PID 1 的
  UID/GID 均为 `10001`。应用用户可读副本，但不可读原始 Secret。
- tmpfs 为 `64 KiB`、`noexec,nosuid,nodev`；关闭 Phase 2B1 后不生成暂存 Secret。
- Compose、container inspect、image history 和日志 Secret 扫描通过；仅 80/443 对外发布。

### 真实 DeepSeek 请求与零扣费

只临时开放测试用户 `y8gau525t593nd9`。任务
`9e183241-81bf-4ae9-ad03-e64bb04a83dd` 使用
`phase2b1_txt_evidence_summary`，由 `deepseek / deepseek-v4-flash` 执行成功：

| 用量或费用 | 验收值 |
|------------|--------|
| input / cached / cache miss tokens | 2891 / 0 / 2891 |
| output / total tokens | 582 / 3473 |
| 输入拆分 / 总数校验 | `input_split_ok=true`、`total_tokens_ok=true` |
| usage / 请求发送 | `usage_reported=true`、`http_request_sent=true` |
| Provider 请求 ID | 存在，仅保留于内部记录 |
| Provider 成本 USD / CNY | `0.001020140` / `0.006918` |
| 用户扣费 | `customer_charge_cny=0`、公开 `charged_cny=0` |

公开结果 `real_ai_analysis=true`、`billing_status=not_billable`，引用真实 `P000xxx`
段落 ID；Provider 请求 ID 和内部成本均未暴露到公开结果。

`online_billing_reservations`、`online_wallet_transactions`、`online_recharge_orders`、
`online_wallet_accounts` 均为 0；所有 usage ledger 的 `customer_charge_cny` 合计为 0。
生产验收值只证明本次明确列出的现场场景；429、未知调用和崩溃恢复等原有 Fake/本地
回归证据仍按原范围保存，本轮没有补写未提供的真实故障注入结果。

真实验证完成后开关已关闭、白名单已清空；API healthy、Worker 正常运行、网站 HTTP 200，
`PRODUCTION_LOG_SAFETY=OK`。这构成生产白名单验收闭环，不等于向公网用户开放模型费用。

## 下一阶段进度与优先级

1. **轻量化 Web/API 部署机制**：`CHG-20260903-001` 已新增本地实现和离线回归，
   仍待香港隔离验收，尚未部署。Web 只更新 Web，普通 App 更新仅作用于 API/Worker；
   默认拒绝高风险/未知/混合变更，App 跳过数据库初始化。全局 `current` 保持完整基础设施
   基线，以 `current-web` / `current-app` 和受限 Compose override 记录组件部署；健康或
   指针失败回滚旧镜像。工具自身属于 full，首次安装需人工完整验收。
   Protocol 2 已补稳定 bin、root 专属版本化工具安装和独立 project 的 D–G 验收入口；
   d6416111 bootstrap 已 superseded。隔离模式独立内部网络、无宿主端口，仅使用显式假 Secret，
   不从 current 加载工具代码。操作说明及剩余门禁见 `infra/online/README.md` 和
   `infra/online/ACCEPTANCE.md`，不得把离线 Fake 测试视为生产切换证据。
2. **UI 与产品流程优化**：在轻量部署机制可验收后，优化现有注册/登录、上传 TXT、任务进度、
   结果和失败反馈流程；不借此开放模型选择、公共白名单或收费业务。

真实全书分析、充值、钱包、正式计费、公开 onboarding、多模型、桌面端改造与正式版本发布
仍不在本轮范围。后续需另行批准范围和验收门禁；当前生产开关继续关闭，白名单继续为空。
