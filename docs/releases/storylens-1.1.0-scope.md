# StoryLens 1.1.0 Scope Freeze（范围锁定）

**Status:** Frozen (STEP 2.0); **AMENDED BY CHG-20260726-004** (Free entitlement)  
**Version target:** 1.1.0（尚未 bump `VERSION`；当前源码仍为 `1.0.5`）  
**Change:** CHG-20260725-003 (tech) + CHG-20260726-004 (Free / Pro boundary)  
**Date:** 2026-07-25 / amended 2026-07-26  
**Architecture truth:** [storylens-whole-book-architecture.md](../architecture/storylens-whole-book-architecture.md)  
**Public Base (STEP 2.0 start):** `eaa278d419aac847321254f32a4424db139b814d`  
**Private Base:** `727f886ead297a3af2019354f2f56352cf22a9d4`  
**Free baseline:** `v1.0.5` / `release/1.0.5` / `ddae7ee4910ab35a443e47fc1ffad4928e7a5543`

> 本文冻结 **1.1.0 产品与工程范围**。本文不是功能实现，也不替代正式发布说明 `docs/releases/1.1.0.md`（后者仅在 `prepare-next-release` 后生成）。

**Product boundary (CHG-20260726-004):**

```text
StoryLens 1.1.0 唯一新增功能：Free 原生全书概览
Public 客户端：开源
原生全书概览使用权：免费
Private Native Overview Engine：闭源
第三方 Provider API 费用：由用户账户承担
Pro 正式起点：1.2.0（不得在 1.2.0 把已免费的原生概览收回为 Pro 专属）
```

对外建议表述：StoryLens 客户端开源，原生全书概览免费使用；部分分析引擎组件以闭源方式随产品提供。  
不得声称「原生全书概览全部开源」或「整套 StoryLens 完全开源」。

---

## 1. 版本定位

### 1.1 唯一正式新增功能

```text
中文：原生全书概览
英文：Native Whole-Book Overview
Entitlement：FREE（StoryLens 1.1.x）
```

用户**无需**预先执行全部单章分析。  
第一事实源：**完整小说原文 + Book Snapshot**。

### 1.2 “完整”的含义

完整 = **原生全书概览**具备产品闭环，**不是** 全部 Pro 模块完成。

必须同时满足：

```text
入口完整 · 执行完整 · 数据完整 · 错误完整 · 恢复完整 · 结果完整 · Evidence 完整 · 门禁完整 · 发布完整
```

### 1.3 命名隔离（不得混名）

| 名称 | 含义 |
|------|------|
| **原生全书概览** | 直接分析完整小说原文，不要求提前完成全部单章分析（1.1.x Free） |
| **章节聚合洞察** | 聚合已完成的单章精细分析资产（既有 Pro 能力，独立页面保留） |
| **Private Engine** | 闭源实现边界；Private ≠ Paid |

---

## 2. 用户流程（冻结）

1. 用户已导入小说（TXT / DOCX / EPUB）→ 稳定 `Book` / `Chapter` / `Paragraph`。  
2. 在书籍工作区点击 **「原生全书概览」**（Free；无需 Pro License）。  
3. 进入 **分析前检查页（Preflight）**，至少显示：  
   - 小说名称、章节数、段落数、总字数  
   - 分析模式（1.1.0 默认 `whole_book_native`）  
   - Provider、Model  
   - 预计 Token、预计费用（第三方 API，由用户账户承担）  
   - Feature Flag / 原文完整性状态  
4. 用户确认后创建 **正式 Whole-Book Run**。  
5. 展示进度 / 错误 / Retry。  
6. 完成后展示 Overview 结果与 Evidence；可跳转段落；重启后可重新打开 Completed Result。

**不得要求**用户预先完成 Scene Pipeline、Reader Journey、单章钩子/节奏分析或全部章节 AI 分析。

---

## 3. 正式执行链（冻结）

```text
Feature Flag + Provider/Consent/Budget 校验（Native Overview 不要求 Pro License）
→ 冻结 Book Snapshot
→ 创建 Whole-Book Run
→ 创建真实 Run Stages
→ 基于完整原文建立跨章节窗口
→ 调用 Private Overview Engine
→ 生成候选实体、资产和 Evidence
→ Public 校验、去重和持久化
→ 保存窗口 Checkpoint 和 Usage
→ 处理后续窗口
→ 生成 Overview Projection
→ 展示结果和 Evidence
```

---

## 4. Must Have（必须完成）

### 4.1 入口完整

- [ ] 用户可发现入口「Pro 原生全书概览」  
- [ ] Free 用户可见 Pro 提示或升级入口，且**不能**仅靠前端隐藏绕过后端  
- [ ] Provider 未配置时有明确错误码与文案，禁止静默失败  
- [ ] 空书 / 无有效段落 / Snapshot 无法建立时拒绝启动，并返回可识别错误  

### 4.2 执行完整

- [ ] 正式 Run：至少支持 `create` / `read` / `retry` / `resume`  
- [ ] 绑定 Completed Snapshot  
- [ ] 读取完整原文；跨章节窗口覆盖全部有效 Paragraph（有重叠）  
- [ ] 调用真实 Provider（L4/L5 证据；契约测试可用 FakeHttp，**不得**用 Mock 冒充正式结果）  
- [ ] 真实 Stage 状态写入 DB  
- [ ] Usage / 费用写入 DB  

### 4.3 正式 Stage（本版本实际执行）

```text
snapshot_preflight
build_context_windows
extract_overview_facts
materialize_assets
generate_overview_projection
finalize
```

规则：

- 可保留现有 10-stage 协议键；**未执行的 Stage 不得标记为 completed**。  
- **不得**将 `build_fulltext_index` 解释为 FTS5 已实现（FTS5 不在 1.1.0）。  

### 4.4 数据完整（统一 `storylens.db`）

必须持久化：

```text
Snapshot · Run · Stage · Entity · Asset · Asset Version · Evidence ·
Result Projection · Usage · Checkpoint
```

禁止正式结果仅存在于：前端状态、临时 JSON、日志、Private 内存。

### 4.5 最小 Entity / Asset / Evidence

**Entity（至少）：** Character、Character Alias；Location / Organization / Object 按需。  

**Asset（至少，可用当前 Enum 映射）：**

| 目标语义 | 当前 Enum 映射（优先映射，不大重构） |
|----------|--------------------------------------|
| Plot Event | `event` |
| Character Goal | `goal` |
| Conflict | `conflict` |
| Information Reveal | `reveal` |
| State Change / Ending State | 可用等价结果表达；缺省类型不强制新 Enum |

**Evidence 至少字段：** `book_id` · `snapshot_id` · `chapter_id` · `paragraph_id` · `source_run_id` · `evidence_role` · `confidence` · quote 或定位摘要。  
不得把大量整章正文作为 Evidence 重复存储。

### 4.6 Materializer（最小）

Candidate Schema 校验 · Entity Resolution · Alias 合并 · Asset 去重 · Evidence 范围校验 · Source Run 绑定 · Asset Version · 事务回滚 · 幂等键。  
**不做**完整资产编辑平台。

### 4.7 Overview 结果字段

**必须保留（不可因时间牺牲）：**

1. 主角  
2. 主角核心目标  
3. 全书主要矛盾  
4. 核心悬念或核心问题  
5. 关键转折  
6. 结局状态  
7. 一句话故事  
8. 全书概要  
9. 上述重要结论的 Confidence + Evidence（Chapter / Paragraph / 正文跳转）  

**完整目标字段集（可降级复杂度，见 §13）：**  
小说类型 · 主要叙事特征 · 核心设定 · 主角 · 核心目标 · 主要矛盾 · 核心问题 · 关键转折 · 高潮 · 最终解决的问题 · 结局状态 · 一句话故事 · 全书概要。

不可靠字段允许显示「暂未能可靠判断」；**禁止猜测填满**。

### 4.8 错误完整（可验证）

至少覆盖并有自动化或手工清单证据：

| 场景 | 可验证条件 |
|------|------------|
| Pro 授权缺失 | HTTP/API 返回授权类错误码；结果不写入正式 Overview |
| Provider 未配置 | Preflight 或 create 拒绝；文案可定位 |
| Provider 超时 | Run/Stage 进入失败态；可 Retry |
| Provider 非法数据 | 拒绝 Materialize；不产生伪造正式资产 |
| Evidence 无效/越界 | 拒绝持久化或标记无效；不伪造跳转 |
| 数据库写入失败 | 事务回滚；无半写入 Checkpoint/资产不一致 |
| Snapshot 无效 | 拒绝启动或失败态可诊断 |
| Run 已存在 | 幂等或明确冲突错误，不静默双写 |
| 应用中断 | 重启后可 `read` Run |
| 部分窗口失败 | 已完成窗口不重复调用；失败窗口可 Retry |

### 4.9 恢复完整（可验证）

- [ ] 已完成窗口不重复调用 Provider  
- [ ] 失败后 Retry 可用  
- [ ] 应用重启后可读取 Run  
- [ ] Completed Result 可重新打开  
- [ ] Retry 不产生明显重复资产（同幂等键）  
- [ ] Retry 不重复处理已完成窗口  

### 4.10 License / 授权完整

- [ ] 后端 Capability / License Gate 强制  
- [ ] Free 无法通过改前端路由获得正式 Overview 结果  

### 4.11 Free 回归与发布完整

- [ ] Free 1.0.5 核心路径回归通过（导入 / 书库 / 单章分析入口 / 删除保护 / 原始文件不删）  
- [ ] 1.0.5 数据库**副本** `create_db` 升级成功且不改写用户正式库  
- [ ] Windows 安装包可启动；Private Engine 正确装载  
- [ ] 真实 Provider + 真实小说可完成至少一次 Overview  
- [ ] 重启后 Completed 结果仍在  

### 4.12 原文窗口

- [ ] 稳定 Paragraph ID 定位  
- [ ] 保留 Chapter 边界；支持跨章；相邻窗口重叠  
- [ ] 所有有效 Paragraph ≥ 1 个窗口  
- [ ] Window Input Hash + 窗口顺序  
- [ ] 已完成窗口可跳过  
- [ ] **不依赖**单章分析结果  

### 4.13 最小全局状态（Overview 所需）

```text
已识别人物 · 人物别名 · 主角候选 · 核心目标候选 · 主要冲突候选 ·
核心问题候选 · 关键事件候选 · 高潮候选 · 结局状态候选 · 已处理窗口
```

延期：钩子生命周期、关系演变、双时间线、完整人物/读者知识状态（STEP 3–6）。

---

## 5. Non-Goals（明确延期，不得进入 1.1.0）

### 5.1 其他整书模块产品页

全书结构阶段 · 章节功能地图 · 主线支线 · 人物弧 · 人物关系 · 目标—冲突—选择—后果完整链 · 钩子生命周期 · 因果链 · 双时间线 · 原生整书阅读旅程 · 完整诊断系统。

### 5.2 数据与平台

FTS5 正式实现 · Neo4j · 向量库 · 大型资产库 · 批量资产编辑 · 跨书比较 · 灵感库 · 故事实验台 · 增量局部重分析 · 完整用户确认工作台。

### 5.3 UI

大规模设计重构 · 新设计系统 · 大型图谱可视化 · 全局导航重构 · 与 Overview 无关的页面美化。

### 5.4 WIP

Structure Empty Policy WIP **不合入**；不处理与 Overview 无关的历史 WIP。

---

## 6. 数据闭环（写入顺序）

```text
License OK
→ Snapshot（冻结 / 绑定）
→ Whole-Book Run 行
→ Stage 行（仅实际执行者）
→ Context Windows + Input Hash
→ Private Candidate
→ Public Materialize：Entity / Alias / Asset / Version / Evidence
→ Checkpoint + Usage
→ 下一窗口 …
→ Overview Projection（缓存允许；非唯一事实源）
```

单一业务库：`%LOCALAPPDATA%\StoryLens\database\storylens.db`。Private **不**建库、不 ORM、不 Migration。

---

## 7. 已有能力复用矩阵

| 已有能力 | 1.1.0 处理 | 当前诚实状态 |
|----------|------------|--------------|
| Free Book/Chapter/Paragraph | 直接复用 | Production |
| Book Snapshot | 复用并补正式 Run 绑定 | Production 骨架 |
| Native/Enhanced Mode | 复用；默认 Native | Contract + 部分实现 |
| Context Pipeline | 复用并产品化窗口执行 | Lab/Contract 偏多 → 产品化 |
| Run Stage ORM | 复用并补正式执行 | ORM 已有；正式入口未启用 |
| Entity/Asset/Relation/Evidence ORM | 复用 | Production 骨架 |
| Private Book Overview Contract | 复用并接入生产链 | Contract / Lab |
| Citation Repair | 复用 | Private 能力 |
| Capability/License Gate | 复用 | Production（章节聚合洞察已用） |
| 章节聚合洞察 | **保留独立辅助页** | UI 已集成 |
| Lab Executor | 参考，非 Production | Lab |
| FakeHttp | 契约测试；非上线证据 | Fixture |
| Structure WIP | **不合入** | WIP |

---

## 8. 错误与恢复闭环（摘要）

见 §4.8 / §4.9。Pause/Cancel **用户操作**可不完整，但数据模型不得阻塞后续增加；不得因实现 Pause 延误正式闭环。

---

## 9. 测试层级（L1–L5）

| 层级 | 何时 | 范围 |
|------|------|------|
| L1 | 每次文件修改后 | 单元 / Schema / Mapper / Validator / Component |
| L2 | 每个 Agent Commit 前 | Service / Repository / Private Runner / API / UI Workflow |
| L3 | 每个 Commit 进入 Integration 后 | Contract / Adapter / Database / License / Free 受影响回归 |
| L4 | 真实运行门禁 | ≥1 短篇 + ≥1 中等长度；真实 Provider；真 Snapshot/Asset/Evidence/费用；Retry；重启 |
| L5 | 发布门禁 | 1.0.5 DB 副本升级；Free 核心回归；Windows 安装；Sidecar；License；Provider；Pro Overview；Updater；退出清理 |

禁止：用 Mock/FakeHttp 结果作为 L4/L5 正式通过证据。

---

## 10. 发布阻断条件

### P0（任一不满足 → 不得发布）

- Free 1.0.5 功能被破坏  
- 数据库升级破坏旧数据  
- Private 建立第二数据库  
- Pro License 可绕过  
- 原文存在静默遗漏（有效 Paragraph 未进任何窗口）  
- 结果不绑定 Snapshot  
- Evidence 无法定位  
- Retry 大量重复写资产  
- Completed 结果重启后丢失  
- Windows 安装包无法启动  
- 真实 Provider 无法跑通  
- 使用 Mock 结果冒充正式结果  

### P1（须关闭，或书面决定延期/降级字段，禁止静默上线）

- 费用估算明显错误  
- Provider 失败状态不清楚  
- 空结果界面不可理解  
- 部分字段无 Evidence 却显示高置信度  
- 超长小说无明确限制或提示  
- 运行中删除书籍未被阻止  
- 结果页严重渲染或路由错误  

---

## 11. 并行开发边界（STEP 2.1 契约冻结后生效）

| 轨道 | 负责 | 禁止 |
|------|------|------|
| **A** Public 数据与运行 | Run / Snapshot / Stage / Window / Checkpoint / Repository / Materializer / API / License Gate / Usage | Private Prompt；React 页面；共享契约；未经 I 委派的 Migration |
| **B** Private Overview Engine | Input/Output / Prompt / Candidate / Citation / Repair / 最小全局状态更新策略 / Provider Contract | SQLite；Public ORM/Migration；前端；License 存储；Windows 路径 |
| **C** 产品前端 | Preflight / Cost / Progress / Error / Retry / Result / Evidence / License Required / API Client | 后端业务；DTO；Migration；Private；Free 单章业务 |
| **D** 只读审计 | Diff 审查 | 自行改业务代码 |
| **I** Integration | Migration；共享 DTO；公共 Enum；Capability Registry；状态机；错误码；Integration 分支；Change Registry；合并门禁 | — |

STEP 2.G2 未通过不得扩展功能；最后 3 小时只修 P0/P1，禁止加新能力。

---

## 12. 时间切片（建议占比）

| 阶段 | 建议占比 |
|------|----------|
| STEP 2.0 范围锁定 | 5% |
| STEP 2.1 契约和数据库冻结 | 15% |
| STEP 2.2 行走骨架 | 15% |
| STEP 2.3 并行完整实现 | 30% |
| STEP 2.4 集成与错误修复 | 15% |
| STEP 2.5 真实运行 | 8% |
| STEP 2.6 Free 回归 | 5% |
| STEP 2.7 Windows 发布 | 7% |

范围无法稳定完成时：**缩减 Overview 可选字段复杂度**，不得牺牲数据一致性、Evidence、License、失败恢复、Free 兼容。

---

## 13. 可降级 vs 不可牺牲

**可降低复杂度：** 小说类型细分类、复杂叙事特征、高潮多层解释、多主角并列、多条次要转折、高级诊断、精细视觉。  

**不可牺牲：** 原文第一事实源、Snapshot、Run、Asset/Evidence 持久化、后端授权、Retry、重启后读取、Free 回归、§4.7 必须保留字段。

---

## 14. 人工验收清单（G8 预备）

验收人按下列勾选（每项须有实际操作证据，禁止「基本可用」）：

1. [ ] Free 用户打开入口见升级提示；直接打正式 Overview API 被拒绝  
2. [ ] Pro 用户 Preflight 显示章节/段落/字数/Provider/费用/授权/原文完整性  
3. [ ] 创建 Run 后进度可见；中断应用后可重新打开同一 Run  
4. [ ] 完成后可见主角/目标/矛盾/问题/转折/结局/一句话/概要  
5. [ ] 至少 3 个重要结论可点击 Evidence 跳到对应段落  
6. [ ] 故意断网/错误 Key 后错误可读，Retry 后不重复计已完成窗口  
7. [ ] 重启应用后 Completed Overview 仍存在且绑定同一 Snapshot  
8. [ ] Free：导入 TXT、打开书库、单章分析入口、删除二次确认仍可用  
9. [ ] 在 1.0.5 数据库**副本**上升级后，旧书仍可打开  
10. [ ] Windows 安装包冷启动成功；Pro Overview 可走通一次真实 Provider  

---

## 15. 下一步

```text
STEP 2.1 契约和数据库冻结
```

本文件通过 STEP 2.0-GATE 后，**不得自动**修改 Migration / DTO / 打开正式 Run / bump VERSION / Push。

---

## 16. 变更记录

| 日期 | Step | 说明 |
|------|------|------|
| 2026-07-25 | STEP 2.0 | 首次冻结 1.1.0 Native Overview 范围 |
