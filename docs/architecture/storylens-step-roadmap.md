# StoryLens Step 路线图与 Cursor Prompt 模板（正式真值）

**Status:** Frozen (STEP 1.3)  
**Change:** CHG-20260725-003  

配套总架构：[storylens-whole-book-architecture.md](./storylens-whole-book-architecture.md)

---

## 1. 版本与 Step 总图

| Step | 版本意图 | 主题 |
|------|----------|------|
| STEP 0 | 1.0.5 Free | Free 基线封存 |
| STEP 1 | 1.1.0 前置 | 架构收敛（含 1.1 现场冻结、1.2 语义纠正、1.3 架构冻结） |
| STEP 2 | **1.1.0** | 原生全书概览（唯一正式 Pro 切片） |
| STEP 2.9 | 1.1.1 | 稳定版 |
| STEP 3 | 1.2.0 | 统一叙事事实底座 |
| STEP 4 | 1.3.0 | 结构、故事线、章节功能 |
| STEP 5 | 1.4.0 | 人物动力系统 |
| STEP 6 | 1.5.0 | 钩子、因果、双时间线 |
| STEP 7 | 1.6.0 | Pro V1 综合完成（含原生整书阅读旅程等） |
| STEP 8 | 2.0.0 | 叙事资产与辅助创作平台 |

> STEP 2 = 1.1.0。Overview 是首个完整 Pro 产品切片，**不**代表 Pro V1 全部完成。

---

## 2. 轨道定义

| 轨道 | 职责 |
|------|------|
| **A** | Public 数据与运行（ORM/Repo/Run/Orchestrator 等，按 Step 文件域） |
| **B** | Private Engine |
| **C** | 产品前端 |
| **D** | 质量审计（只读；发现 P0 退回，不自行改业务） |
| **I** | Integration（合并、共享契约、Migration、公共 Enum、Capability Registry、门禁） |

规则：

- 每个 Agent 只能修改自己的文件域。  
- **Migration、共享 DTO、公共 Enum、Capability Registry 只能由 Integration Agent 修改。**  
- STEP 2.G2 前禁止大规模多 Agent 并行。  
- 每个小 Commit 合入后立即定向测试；不得最后统一补测试。  
- 自动开发只能推进到 `tested`；**`verified` 必须由用户人工决定。**  
- 默认：**允许本地 Commit；禁止 Push；禁止 verified。**

---

## 3. 门禁（G0–G8）

| 门禁 | 含义 |
|------|------|
| G0 | 基线门禁（Tag/Branch/工作树/VERSION） |
| G1 | 契约 / 产品语义门禁 |
| G2 | 行走骨架 |
| G3 | 并行模块 |
| G4 | 集成 |
| G5 | 真实运行 |
| G6 | Free 回归 |
| G7 | Windows 发布 |
| G8 | 用户人工验收 |

STEP 1 子门禁示例：`1.G0`（现场冻结）、`1.G1`（语义纠正）、`1.3-GATE`（架构冻结）。

---

## 4. STEP 1 完成状态（Current）

| 子步 | 状态 |
|------|------|
| STEP 1.1 现场和版本冻结 | PASSED（1.G0） |
| STEP 1.2 产品语义纠正 | PASSED（1.G1） |
| STEP 1.3 架构决策冻结 | 本文件所属门禁 |

下一步：**STEP 2.0 1.1.0 范围锁定**（不得自动进入）。

---

## 5. 统一 Cursor Prompt 模板

每个 Step / Agent 任务必须包含：

```text
STEP：
版本：
Change ID：
轨道：
负责人：
前置门禁：
允许修改文件：
禁止修改文件：
输入契约：
输出契约：
必须测试：
完成门禁：
是否允许 Commit：
是否允许 Push：NO
是否允许 verified：NO
```

附加硬性约定：

- Structure Empty Policy WIP 等受保护工作树：禁止 reset / clean / restore / stash / merge / rebase / 删除 / 自动提交 / 自动合入。  
- Free `v1.0.5` / `release/1.0.5`：禁止移动 Tag、重建 Tag、覆盖分支、改写历史。  
- 日常禁止修改 `VERSION`；禁止未确认的 bump / 正式构建 / 发布。  

---

## 6. Change Registry 约定

- 功能变更登记：`release/changes/CHG-*.json` + `release/unreleased.json`  
- 状态机：`registered → implemented → tested → verified → ready-for-staging → ready → released`  
- Commit trailer：`StoryLens-Change: CHG-...`；可用 `StoryLens-Step: STEP-...`  
- 架构冻结类工作保持 `implemented`，不得因写文档单独升到 `verified`  

---

## 7. 变更记录

| 日期 | Step | 说明 |
|------|------|------|
| 2026-07-25 | STEP 1.3 | 路线图与 Prompt 模板冻结 |
