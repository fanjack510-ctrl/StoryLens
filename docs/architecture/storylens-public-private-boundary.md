# StoryLens Public / Private 责任边界（正式真值）

**Status:** Frozen (STEP 1.3)  
**Change:** CHG-20260725-003  
**Supersedes on conflict:** phase-level boundary notes under `narrative-intelligence-core/` for **product ownership** questions; phase docs remain valid for historical contract IDs.

---

## 1. 原则

StoryLens 采用 **Public 开源产品仓 + Private 闭源引擎仓**。  
业务事实只进 **一个** Public 管理的 SQLite；Private 只提供算法与候选，不拥有持久化主权。

---

## 2. Public 开源仓负责

- React / Tauri 桌面框架  
- Free 1.0.5 全部产品功能  
- FastAPI 产品入口  
- License / Capability  
- Provider 凭据与调用入口（经 Credential / Gateway）  
- SQLite、Migration、ORM、Repository、事务  
- Snapshot  
- Whole-Book Run / Run Stage / Checkpoint  
- Usage / Cost  
- Candidate 校验与 Materialize  
- Entity / Asset / Relation / Evidence 持久化  
- Result Projection  
- Evidence 跳转、用户纠正  
- Pro UI 壳（含章节聚合洞察、未来原生 Overview 页）  

---

## 3. Private 闭源仓负责

- Prompt 与闭源规则  
- 算法与跨章节推理  
- 候选实体 / 资产 / 关系生成  
- 全局叙事状态**更新策略**（状态对象本身由 Public 持久化）  
- Citation Repair  
- 低置信度处理  
- 模块级综合推理  

Private 交付形态（sidecar / package / remote / hybrid）由打包策略决定；**不改变**上述责任边界。

---

## 4. Private 禁止直接负责

- SQLite / ORM / Migration  
- License 存储  
- API Key 存储  
- Windows 路径策略  
- Tauri / 前端  
- 正式事务边界  
- 创建 `pro.db` 或任何第二业务库  
- 在 Public 仓落地正式算法与正式 Prompt 正文  

---

## 5. 调用边界（Target）

```text
Public Orchestrator
  → 校验 License / Capability
  → 准备 Snapshot / Window / Global State 摘要
  → 调用 Private Engine（协议 / DTO）
  → 接收 Candidate
  → Public 校验、落库、计费、Checkpoint
```

模块与引擎实现不得：

- 直连 Bailian / OpenAI / llama-server（须经 Provider Gateway）  
- 在模块内读取 API Key  
- 绕过 Public 校验直接写库  

详见既有 `phase2b-private-engine-boundary.md`（接口层约定）。

---

## 6. 与当前代码的对齐（Current）

| 项 | 状态 |
|----|------|
| Public `private_engine_contract/` | 已存在 |
| Private package 协议实现 | 已存在（Integration Private HEAD） |
| 正式 `POST .../whole-book-runs` | **禁用** |
| Lab 路径 `/api/v1/labs/...` | 存在；非生产 |
| Private 无独立 SQLite | **Current 核验：无 create_engine / sessionmaker** |

---

## 7. 变更记录

| 日期 | Step | 说明 |
|------|------|------|
| 2026-07-25 | STEP 1.3 | 产品级边界冻结 |
