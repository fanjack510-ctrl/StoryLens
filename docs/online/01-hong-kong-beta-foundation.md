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

## Phase 2B1 本地实施状态（等待香港私有验收）

`CHG-20260830-005` 在 Phase 2A 链路上增加了一个默认关闭、白名单为空的内部真实分析
门禁。本次只形成待部署包，不改变上述已经 verified 的香港生产基线：

- 新 pipeline 固定为 `phase2b1_txt_evidence_summary`；`phase2a_smoke` 仍是默认值；
- Provider 固定为阿里云百炼华北 2 OpenAI 兼容接口，模型固定为
  `qwen3.7-plus-2026-05-26`；浏览器和 API 不能选择 Provider、URL 或模型；
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
provider_cost_cny =
  ((输入 token - 缓存输入 token) × 2 + 缓存输入 token × 0.4 + 输出 token × 8)
  / 1,000,000
```

价格版本为
`aliyun-cn-beijing-qwen3.7-plus-2026-05-26@2026-08-30`。单任务最多两次 Provider
调用，发送前按本次最坏成本叠加既有实际成本检查 `0.35 CNY` 上限。

## Phase 2B1 香港私有验收门禁

在人工放置真实 Secret 后，只能先在隔离环境为一个内部白名单账户开启。正式切换前必须
验证：真实请求成功、Provider usage 与内部账本逐项相符；429 和无效结构的两次尝试都被
汇总；读取超时及崩溃遗留不会再次调用；日志不含 Secret、TXT、Prompt 或原始响应；API、
Web 和其他容器没有 Provider Secret；`phase2a_smoke` 保持零 Provider 调用；所有钱包类表
保持零写入。通过这些门禁前，Phase 2B1 不视为生产完成。

本阶段仍不包含公开付费、钱包扣款、爱发电充值、多模型、桌面端改造或正式版本发布。
