# StoryLens Online：香港 Beta 状态与路线图

## 当前结论

Phase 2A 在其冻结范围内已完成实现、香港服务器部署和真实环境验收，完成度为
**100%**。这表示用户任务闭环及其生产运行基础已经通过，并不表示真实模型分析、
充值和正式计费已经上线。

当前线上基线：

| 项目 | 状态 |
|------|------|
| 代码提交 | `ad89605651439ede3ed52692111fcda2b6848e5a` |
| 正式目录 | `/opt/storylens/releases/ad896056` |
| 当前软链接 | `/opt/storylens/current` 已指向正式目录 |
| 网站根地址 | HTTP 200 |
| API / Web / PocketBase / PostgreSQL / Redis | healthy |
| Worker | 正常运行 |
| `pocketbase-init` | 正常 `Exited (0)` |
| 生产日志安全 | `PRODUCTION_LOG_SAFETY=OK` |
| 根目录版本 | `VERSION=1.3.6`，未因 Online Beta 修改 |
| Git 发布动作 | 未推送、未发布、未创建标签 |

隔离验收使用的容器、数据卷和临时文件已经清理。正式 Secret、备份和回滚镜像继续
保留。部署证据的规范化记录位于
`release/changes/CHG-20260830-004.json`。

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

## Phase 2A 当前限制

- Worker 只生成确定性测试结果，不调用真实模型；
- 不查询或核销爱发电订单；
- 不执行充值到账、钱包冻结、结算或退款；
- 不创建模型用量账单，Phase 2A 任务费用保持为零；
- 尚未接入桌面端已有的完整拆书流水线；
- 当前服务是香港 Beta 运行基线，不等同于 GitHub 正式版本发布。

## 下一阶段建议：Phase 2B（仅规划）

下一阶段应只完成一个最小的“真实分析 + 可审计付费”纵向闭环，建议按以下顺序推进：

1. **事务型钱包与充值账本**：定义余额、充值、冻结、结算、释放和退款的不可变账目，
   使用 PostgreSQL 事务和唯一约束保证幂等。
2. **爱发电订单核销**：服务端查询和校验订单，将订单号映射为一次性充值事务；重复
   回调、重复提交或未知套餐不能重复入账。
3. **分析费用状态机**：分析前预估并冻结，模型成功后按真实输入/输出 Token 成本的
   `2.0` 倍统一结算，平台失败释放冻结，所有金额使用 Decimal 且可对账。
4. **服务端 Provider 网关**：只从服务器 Secret 读取模型凭据，复用统一 Provider 协议；
   不把桌面 API Key、管理员 Secret 或内部异常暴露给浏览器。
5. **单一真实分析闭环**：先只接一个受控 TXT 分析类型，覆盖提交、执行、进度、结果、
   重试、幂等和账单关联，不同时扩展多种分析产品。
6. **生产门禁**：加入充值/结算并发测试、故障注入、成本上限、审计导出、备份恢复和
   香港隔离环境端到端验收，再决定是否扩大 Beta。

Phase 2B 不应同时引入多模型投票、图数据库、LoRA、完整写作工作台或桌面端改造。
正式实现前应另建 Change ID，冻结金额精度、订单幂等键、任务状态机、Provider 价格版本
和失败责任边界。
