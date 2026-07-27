# StoryLens Cursor Prompt｜STEP 2.4 滚动集成与失败路径收敛

## 1. 任务标识

```text
STEP：2.4
阶段名称：滚动集成与失败路径收敛
版本目标：StoryLens 1.1.0
Change ID：CHG-20260725-003
主轨道：I
协作轨道：A / B / C
审计轨道：D
前置门禁：STEP 2.G3 = PASSED
目标门禁：STEP 2.G4
```

本阶段不增加产品功能。

唯一目标：

> 将 STEP 2.3 已完成的 Public、Private、UI 生产形态实现真正连接起来，通过失败注入、事务测试、恢复测试和跨轨集成关闭问题。

---

## 2. 开始前必须读取

```text
docs/architecture/storylens-whole-book-architecture.md
docs/architecture/storylens-public-private-boundary.md
docs/architecture/storylens-step-roadmap.md
docs/releases/storylens-1.1.0-scope.md

docs/contracts/storylens-1.1.0-native-overview-contract.md
docs/contracts/storylens-1.1.0-native-overview-error-codes.md
docs/contracts/storylens-1.1.0-native-overview-state-machine.md
docs/contracts/storylens-1.1.0-native-overview-database.md

release/changes/CHG-20260725-003.json
release/evidence/CHG-20260725-003/night-run/gate-2g3.md
```

开始前记录：

```text
Public Integration HEAD
Private Integration HEAD
Public status
Private status
VERSION
Feature Flag default
Fixture Hash
Structure WIP status
剩余时间
剩余 API 预算
```

必须使用 `STEP 2.G3` 完成后的实际 HEAD，不得使用旧 Prompt 中的历史 HEAD。

---

## 3. 允许和禁止

### 允许

* 修复 STEP 2.3 引入或暴露的 P0/P1；
* 修复 Public/Private Adapter 集成；
* 修复事务和幂等；
* 修复 Retry/Resume；
* 修复错误码映射；
* 修复 UI 状态；
* 补失败注入测试；
* 补 Free 受影响回归；
* 本地 Commit；
* 本地 Integration。

### 禁止

* 新增整书业务模块；
* 开发 Structure；
* 开发 Storylines；
* 开发人物弧；
* 开发钩子、因果、双时间线；
* 开发整书 Journey；
* 修改正式 VERSION；
* 打开 Feature Flag 默认值；
* 真实 Provider 调用；
* Windows 构建；
* Push；
* Tag；
* Release；
* verified。

---

## 4. 工作方式

采用：

```text
I：跨轨 Integration 和共享问题
A：Public 运行、事务、恢复
B：Private Parser、Repair、Transport 错误
C：前端错误、恢复和结果状态
D：逐提交只读审计
```

原则：

* 一个问题只能有一个负责人；
* 不得多个 Agent 同时修同一文件；
* 每个修复一个小 Commit；
* 每个 Commit 立即跑定向测试；
* D 审计通过后才滚动合入；
* 不积累红测试。

---

## 5. 跨轨真实离线调用链

必须验证以下链路不使用 Public 独立业务 Fake：

```text
Public Run Orchestrator
→ Public Engine Loader
→ Private Native Overview Engine
→ Fake Provider Transport
→ Private Prompt
→ Private Parser / Repair
→ Window Result Contract
→ Public Candidate Validator
→ Public Materializer
→ Run State Version
→ Private Synthesis
→ Public Projection
→ API
→ UI
```

允许 Fake 的唯一位置：

```text
ProviderTransport
```

不得 Fake：

* Public Orchestrator；
* Private Engine；
* Materializer；
* Repository；
* SQLite；
* API；
* UI。

必须证明：

```text
Engine ID = private-native-overview-v1 或当前冻结的正式 ID
Transport = fake/deterministic
```

不得使用 Fixture Engine 冒充 Private Engine。

---

## 6. Adapter 和 Contract 一致性

检查：

* Public Engine Protocol；
* Private 实现签名；
* Window Input；
* Window Result；
* Synthesis Input；
* Projection Candidate；
* Contract Version；
* Fixture Hash；
* Error Mapping。

必须测试：

1. 正常 Adapter；
2. Private 模块不存在；
3. Engine ID 不存在；
4. Contract Version 不一致；
5. Private 返回额外未知字段；
6. Private 缺必要字段；
7. Private Engine 抛出预期异常；
8. 禁止静默降级 Fixture。

如 Contract 本身存在 P0：

```text
停止 STEP 2.4
记录 CONTRACT_AMENDMENT_REQUIRED
不得自行改 Contract
```

---

## 7. 失败注入矩阵

### 7.1 Provider 类

必须注入：

```text
PROVIDER_TIMEOUT
PROVIDER_RATE_LIMITED
PROVIDER_UNAVAILABLE
PROVIDER_OUTPUT_INVALID
PROVIDER_OUTPUT_EMPTY
```

检查：

* Provider Attempt 创建；
* Attempt 状态正确；
* Window 不误标 completed；
* Stage 不误标 completed；
* Run 状态为 failed；
* retryable 正确；
* UI 显示用户可理解信息；
* 不展示堆栈；
* 不无限重试。

### 7.2 Private Engine 类

注入：

```text
PRIVATE_ENGINE_UNAVAILABLE
PRIVATE_ENGINE_INCOMPATIBLE
```

检查：

* 不降级 Fixture；
* 不生成结果；
* 不写假资产；
* Run 可诊断；
* UI 显示正确动作。

### 7.3 内容和 Evidence 类

注入：

* Quote 不属于 Paragraph；
* Paragraph 不属于 Snapshot；
* Chapter 与 Paragraph 不匹配；
* Evidence 指向不存在 Candidate；
* Candidate Evidence 为空；
* 同一 Evidence 重复；
* Candidate ID 重复；
* Deduplication Key 重复。

检查：

* 非法 Evidence 不进入 validated；
* 事务正确回滚；
* 低质量结果不伪装成功；
* 错误码符合冻结契约。

### 7.4 数据库和 Materializer 类

注入：

* Entity 写入后 Asset 写入失败；
* Asset 写入后 Version 写入失败；
* Version 写入后 Evidence 写入失败；
* State Version 写入失败；
* Window Checkpoint 写入失败；
* Projection 写入失败；
* Finalize 写入失败。

检查：

```text
不得产生半提交状态
```

如 Provider Attempt 必须独立提交，验证 Attempt 事实保留，但 Window 和资产事务一致。

### 7.5 中断恢复类

场景：

```text
Window 0 completed
Window 1 completed
Window 2 running 时进程中断
```

然后：

* 关闭 Session；
* 新建 Session；
* 重新获取 Run；
* Retry 或 Resume；
* Window 0/1 不重跑；
* Window 2 attempt_count 增加；
* 后续窗口继续；
* 资产不重复；
* Evidence 不重复；
* 最终 Completed。

### 7.6 创建幂等

重复同一：

```text
book_id + client_request_id
```

检查：

* Run 数量不增加；
* Snapshot 不重复；
* Stage 不重复；
* Window 不重复；
* Provider 不重复调用。

### 7.7 Retry 幂等

对同一个 failed Run 连续调用 Retry 两次：

* 不创建新 Run；
* 已完成 Window 不重跑；
* 同一失败 Window 不并发执行两次；
* Asset 不重复；
* Evidence 不重复；
* Provider Attempt 历史保留。

---

## 8. Stage 和状态机一致性

检查全部真实状态：

```text
pending
preparing
analyzing
materializing
synthesizing
completed
failed
paused
cancelled
```

检查六 Stage：

```text
snapshot_preflight
build_context_windows
extract_overview_facts
materialize_assets
generate_overview_projection
finalize
```

必须验证：

* Stage 顺序；
* started_at；
* completed_at；
* attempt_count；
* error_code；
* checkpoint；
* 失败 Stage；
* Retry 后 Stage 恢复点；
* Completed 不可回到 running。

禁止通过直接数据库赋值跳过状态机完成测试。

---

## 9. Usage 和 Cost 一致性

离线测试允许费用为 0，但必须验证记录结构。

检查：

* 每次 Transport Attempt 有记录；
* Input Token；
* Output Token；
* Total Token；
* Cost；
* Provider；
* Model；
* Window；
* Stage；
* Attempt Status。

测试：

* 正常成功；
* Timeout；
* Repair 调用；
* Retry；
* Rate Limit；
* Failed Materialization。

不得因为数据库回滚删除已经真实发生的 Provider Attempt 事实。

---

## 10. UI 集成收敛

必须使用真实 API Client 和 HTTP Mock Server 或项目现有 API 测试方式。

验证：

* Preflight；
* 用户确认；
* Running；
* 多 Stage；
* 多 Window；
* Tokens；
* Cost；
* Failed；
* Retry；
* Paused；
* Resume；
* Completed；
* Refresh；
* Evidence；
* License；
* Provider；
* Engine；
* Snapshot Changed；
* Active Run。

不得：

* 伪造进度；
* 用前端计时器决定完成；
* 直接显示 Private DTO；
* 默认展示内部错误 Detail；
* 混淆“章节聚合洞察”。

---

## 11. Free 受影响回归

本阶段至少跑：

* Book 读取；
* Chapter 读取；
* Paragraph 读取；
* 单章 AnalysisRun 读取；
* Reader Journey 读取；
* 章节聚合洞察 API 和页面；
* Book Workspace；
* 删除保护；
* 活动 Whole-Book Run 阻止删除；
* 原始文件不删除；
* Router Smoke。

不需要本阶段跑完整全量测试。

---

## 12. Commit 拆分

建议：

```text
I1 fix(pro-integration): align public and private native overview runtime
A1 fix(pro-runtime): enforce transactional window materialization
A2 fix(pro-runtime): harden retry and interrupted-run recovery
B1 fix(engine): normalize provider failures and repair outcomes
C1 fix(pro-ui): align native overview recovery and error states
T1 test(pro-integration): add failure injection and recovery matrix
```

每个 Commit：

```text
StoryLens-Change: CHG-20260725-003
StoryLens-Step: STEP-2.4
```

---

## 13. STEP 2.G4 通过条件

必须全部满足：

* [ ] Public 调用真实 Private Engine；
* [ ] Fake 只存在于 Provider Transport；
* [ ] 不静默降级 Fixture；
* [ ] Contract Version 检查；
* [ ] 多窗口离线闭环；
* [ ] Provider 失败矩阵通过；
* [ ] Private Engine 失败矩阵通过；
* [ ] Evidence 失败矩阵通过；
* [ ] Materializer 事务失败矩阵通过；
* [ ] Projection 失败通过；
* [ ] 中断恢复通过；
* [ ] Create Run 幂等通过；
* [ ] Retry 幂等通过；
* [ ] 已完成 Window 不重跑；
* [ ] Asset 不重复；
* [ ] Evidence 不重复；
* [ ] Usage/Cost 记录一致；
* [ ] UI 错误映射完整；
* [ ] Free 受影响回归通过；
* [ ] D-Audit 无 P0；
* [ ] Public Integration clean；
* [ ] Private Integration clean；
* [ ] VERSION 仍为 1.0.5；
* [ ] Feature Flag 默认 false；
* [ ] Structure WIP 未变化；
* [ ] 未执行真实 Provider；
* [ ] 未 Push；
* [ ] 未 verified。

失败则：

```text
STEP 2.G4 = BLOCKED
```

不得进入 STEP 2.5。

---

## 14. Gate 报告

写入：

```text
release/evidence/CHG-20260725-003/night-run/gate-2g4.md
```

必须包含：

```text
Step
Gate
Started
Finished
Public HEAD
Private HEAD
Commits
Adapter Path
Failure Injection Matrix
Transaction Results
Retry Results
Free Regression
Tests
P0/P1/P2
Budget Used
Result
Next Step
```

通过后才能读取 `STEP-2.5-DETAILED.md`。
