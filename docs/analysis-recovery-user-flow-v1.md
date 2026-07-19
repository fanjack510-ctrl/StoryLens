# Analysis Recovery User Flow v1

**Phase:** 1D-C1-UAT-12  
**Product:** Unified Analysis Recovery Center  
**Constraint:** 普通界面不展示内部错误码；不得为每个故障再增加独立竞争按钮。

## 一句话原则

章节页只保留一张「分析已暂停」卡片；系统用统一 Recovery Plan 决定「修复并继续」实际做什么。任务中心只做全局汇总，恢复动作与章节页同一套 API。

## 后端单一事实源

| API | 作用 |
|-----|------|
| `GET /api/v1/analysis-runs/{id}/recovery-plan` | 聚合全部预检（Provider / credential / 请求·Token·费用预算 / Reservation / Scene Artifact / ReaderJourney / stage / 幂等风险） |
| `POST /api/v1/analysis-runs/{id}/recover` | 统一恢复；`recovery_mode=unified`；幂等 `client_request_id` |

遗留边界检查点恢复：`POST .../continue-from-checkpoints`（或 `recover` 且省略 `recovery_mode`）。

### Recovery Plan 输出

`recoverable` · `blockers` · `warnings` · `checks` · `recommended_actions` · `resume_stage` · `will_reuse_artifacts` · `will_create_entities` · `estimated_requests/tokens/cost` · `budget_authorization_proposal`

### 执行顺序（一次返回全部可预检问题）

1. 校验 Run 状态  
2. Artifact 完整性  
3. Provider 配置  
4. readiness refresh  
5. 必要时 reconnect（状态位，不强制设置页测试）  
6. 请求 / Token / 费用预算  
7. 需要授权时返回 proposal  
8. 预算满足后创建或恢复当前阶段实体  
9. 从 `resume_stage` 继续  
10. 更新统一进度  

## 普通用户界面

**标题：** 分析已暂停  

**内容：** 检查项列表（✓ / ✕），例如：

- ✓ Scene分析已完成  
- ✓ 请求额度充足  
- ✓ Token和费用预算充足  
- ✕ AI服务暂未连接  

**按钮：**

| 级别 | 文案 | 行为 |
|------|------|------|
| 主 | 修复并继续 | 调用统一 `recover`（系统按 Plan 自动 reconnect / 临时授权 / resume） |
| 次 | 稍后处理 | 关闭打断，保留可恢复状态 |
| 文本 | 查看详情 | 仅此处可见 internal code / shortfall / provider / model / request_hash / run_id / resume_stage / attempts |

禁止同时出现互相竞争的：「调整额度并继续」「继续生成阅读旅程」「重新连接」「前往任务中心」「重新分析」。

## 用户授权（额度）

涉及额度时弹出 proposal，优先：

**仅为本次Run授权**（`scope=run_temporary`）

展示：当前额度 · 需要额度 · 建议额外额度 · 预计费用 · 不会重跑哪些阶段。

避免要求用户先改全局技术上限。

## Provider 恢复

配置与凭据有效但断开时，「修复并继续」自动：readiness refresh → reconnect → transport/budget recheck → resume。  
仅 credential missing 或 401/403 才跳转设置并定位 API Key。

## 创建前预检

`POST /analysis-runs/preflight` 附带 `full_pipeline_advisory`：Boundary + Scene Analysis + Reader Journey + retry/repair/recovery 余量。不足时创建前一次性说明。

## 状态语义

可恢复统一为用户态 `paused_recoverable`（界面文案：分析已暂停）。  
`reason` 仅进详情：`provider_disconnected` · `request_budget_insufficient` · `token_budget_insufficient` · `cost_budget_insufficient` · `awaiting_reader_journey` · `awaiting_provider_recovery`。  
真正不可恢复才用 `failed`。

## 章节页 vs 任务中心

| 页面 | 角色 |
|------|------|
| 章节页 | 当前任务主恢复入口（统一卡片） |
| 任务中心 | 全局汇总；列表主按钮打开章节同一恢复面 |

两端共用：Recovery Plan · Run Status · Recover Action。

## 实现文件

- `apps/api/app/services/analysis_recovery_center.py`
- `apps/api/app/services/run_scoped_budget_auth.py`
- `apps/api/app/schemas/analysis_recovery.py`
- `apps/desktop/src/components/chapterAnalysis/UnifiedAnalysisRecoveryCard.tsx`
- `apps/desktop/src/pages/BookRoutePage.tsx` / `TasksPage.tsx`
