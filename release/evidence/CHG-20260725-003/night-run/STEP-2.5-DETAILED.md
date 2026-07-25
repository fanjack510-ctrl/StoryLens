# StoryLens Cursor Prompt｜STEP 2.5 真实 Provider 和真实小说验证

## 1. 任务标识

```text
STEP：2.5
阶段名称：真实 Provider 和真实小说验证
版本目标：StoryLens 1.1.0
Change ID：CHG-20260725-003
主轨道：I
执行轨道：A / B
审计轨道：D
前置门禁：STEP 2.G4 = PASSED
目标门禁：STEP 2.G5
```

本阶段只验证现有完整链路。

不允许借真实测试继续增加产品功能。

---

## 2. 用户授权和预算

用户允许真实 API 调用。

绝对费用上限：

```text
¥10.00
```

无人值守夜间安全上限：

```text
¥9.00
```

必须保留：

```text
¥1.00
```

作为计费延迟、Token 误差和异常重试安全缓冲。

任何时候不得主动发起可能让累计费用超过 ¥9.00 的请求。

---

## 3. 开始前读取

```text
STEP-2.5-DETAILED.md
gate-2g4.md
CHG-20260725-003.json
Provider 配置代码
费用和预算代码
当前模型价格配置
```

开始前记录：

```text
Public HEAD
Private HEAD
Public Clean
Private Clean
VERSION
Feature Flag
Provider
Model
已花费用
已保留费用
剩余夜间预算
剩余时间
```

不得在日志中输出 API Key。

---

## 4. 费用台账

创建或更新：

```text
release/evidence/CHG-20260725-003/night-run/provider-cost-ledger.json
```

结构至少包括：

```json
{
  "currency": "CNY",
  "absolute_limit": 10.0,
  "night_limit": 9.0,
  "actual_cost": 0.0,
  "reserved_cost": 0.0,
  "attempts": []
}
```

每次真实请求前记录：

```text
attempt_id
run_id
stage
window_index
provider
model
estimated_input_tokens
max_output_tokens
input_unit_price
output_unit_price
worst_case_cost
actual_cost_before
reserved_cost_before
projected_total
allowed
```

只有：

```text
projected_total <= 9.00
```

才允许调用。

每次调用后记录：

```text
actual_input_tokens
actual_output_tokens
actual_cost
status
error
cumulative_actual
cumulative_reserved
```

如 Provider 暂不返回实际费用：

* 使用真实 Usage 按明确价格计算；
* 若价格无法确认，停止真实调用；
* 不得猜价格。

---

## 5. Provider 自动重试限制

Transport 必须：

```text
网络/Timeout 自动重试最多 1 次
Rate Limit 自动重试最多 1 次
Repair Provider 调用最多 1 次
```

所有调用都计入预算。

禁止：

* SDK 默认无限重试；
* 多 Agent 同时调用真实 Provider；
* 后台不可见重试；
* 失败后自动重新运行整本书。

真实 Provider 调用必须由 Integration 主控串行授权。

---

## 6. 模型选择

优先使用：

* 项目已连通；
* 定价明确；
* JSON 输出稳定；
* 成本较低；
* 当前 StoryLens 支持的模型。

不得永久修改用户默认模型。

如使用低价验证模型而非产品默认模型，必须明确记录：

```text
VALIDATION_MODEL_DIFFERS_FROM_PRODUCT_DEFAULT = YES
```

不得宣称默认模型已通过验证。

---

## 7. 测试样本要求

不得上传用户真实私人小说或未知版权长篇进行无人值守测试。

优先从项目已有合法测试样本中选择。

### 样本 A：极短 Transport Smoke

使用：

```text
行走骨架短篇·灯塔试炼
```

目的：

* 真实 Transport；
* Provider；
* Model；
* JSON；
* Parser；
* Evidence；
* Materializer；
* Projection。

它不作为产品质量样本。

### 样本 B：真实完整短篇

要求：

* 项目测试资产；
* 来源和使用合法；
* 非私人用户作品；
* 结局完整；
* 至少多个章节；
* 可以验证主角、目标、冲突、转折、结局；
* 预计费用可控。

### 样本 C：中等长度作品

只有当：

```text
累计实际费用
+ 当前保留费用
+ 样本 C 最坏预计费用
<= ¥9.00
```

才执行。

预算不够则记录：

```text
MEDIUM_SAMPLE = BUDGET_BLOCKED
```

这不自动阻塞 G5，只要至少一个真实完整 Run 通过，并明确披露中篇未验证。

---

## 8. Live 1：真实 Transport Smoke

执行前：

* 检查 Provider 配置；
* 检查 License；
* 显式启用测试环境 Feature Flag；
* 使用临时数据库；
* 使用正式 Private Engine；
* 禁止 Fixture Engine；
* 费用预估。

验证：

1. Preflight；
2. Create Run；
3. Snapshot；
4. Window；
5. 真实 Provider Attempt；
6. Window Result；
7. Evidence；
8. Materialization；
9. Synthesis；
10. Projection；
11. Completed；
12. UI/API 读取。

检查：

* 真 Provider ID；
* 真 Model ID；
* 真 Usage；
* 真 Cost；
* `engine_id != fixture-native-overview-v1`；
* `prompt_version != fixture-no-prompt`。

失败时：

* 先判断代码 Bug、Provider 问题还是模型输出问题；
* 只允许修 P0/P1；
* 修复后跑离线测试；
* 重新估算预算；
* 再决定是否重试。

---

## 9. Live 2：真实短篇完整 Run

必须使用多窗口样本。

验证：

### 原文

* Snapshot 内容固定；
* 每个 Paragraph 至少进入一个 Window；
* 原文覆盖率 100%。

### 运行

* 六 Stage；
* 多 Window；
* State Version；
* Provider Attempt；
* Token；
* Cost；
* Completed。

### 结果

至少检查：

* 主角；
* 主角目标；
* 主要冲突；
* 核心问题；
* 关键转折；
* 结局状态；
* 一句话故事；
* 全书概要。

### Evidence

逐字段抽查：

* Paragraph 存在；
* Chapter 正确；
* Quote 是正文子串；
* Deep Link 可构造；
* 高置信度字段不缺 Evidence。

### 持久化

* 关闭 Session；
* 新 Session 读取；
* 重启 API 进程后读取；
* Overview 存在；
* Evidence 存在；
* 不依赖 Private 内存。

### Retry

可以使用一次受控失败注入，不必为真实 Provider 再产生额外费用：

* 在真实完成结果之外用离线失败注入验证 Retry；
* 不得为了证明 Retry 故意浪费真实 API 费用。

---

## 10. 质量判定

真实结果不要求文学结论完全等同人工答案，但必须满足：

### 必须

* 无明显捏造人物；
* 无引用不存在段落；
* 无结局与原文相反；
* 主角和目标具备文本依据；
* Evidence 可回溯；
* 不足字段诚实标记；
* JSON 和 Schema 合法；
* Completed 后可持久读取。

### P1

* 核心字段遗漏；
* Synopsis 严重失真；
* Confidence 明显不合理；
* 多窗口状态丢失；
* 结局错误；
* Evidence 虽合法但明显不支持结论。

发现 P1：

* 允许修 Prompt、Parser、Repair 或 Materializer；
* 不允许扩展新模块；
* 修复后先跑离线；
* 剩余预算允许时最多重试一次真实短篇。

---

## 11. 安全停止条件

立即停止真实调用：

* 定价不明确；
* Token 无法估算；
* Projected Total > ¥9.00；
* Actual Cost >= ¥9.00；
* Provider Usage 无法确认；
* 自动重试失控；
* Key 需要被复制到日志；
* 必须修改系统环境；
* 必须读取项目外私人文件；
* 需要使用真实用户正式数据库。

---

## 12. STEP 2.G5 通过条件

必须全部满足：

* [ ] STEP 2.G4 已通过；
* [ ] 费用台账存在；
* [ ] 每次调用前有预估；
* [ ] 夜间实际与保留总额不超过 ¥9.00；
* [ ] 至少一个真实完整 Run 成功；
* [ ] 使用正式 Private Engine；
* [ ] 使用真实 Provider；
* [ ] 使用真实 Model；
* [ ] Provider Attempt 有记录；
* [ ] Token 有记录；
* [ ] Cost 有记录；
* [ ] 多窗口；
* [ ] 原文覆盖率 100%；
* [ ] Entity/Asset/Evidence 真落库；
* [ ] Projection 真落库；
* [ ] Evidence 有效；
* [ ] 新 Session 可读取；
* [ ] API 重启后可读取；
* [ ] 不使用 Fixture 冒充 Live；
* [ ] 无 P0；
* [ ] D-Audit = PASS；
* [ ] Feature Flag 默认仍为 false；
* [ ] VERSION 仍为 1.0.5；
* [ ] 未 Push；
* [ ] 未 verified。

中篇因预算未执行可以通过，但必须明确记录。

---

## 13. Gate 报告

写入：

```text
release/evidence/CHG-20260725-003/night-run/gate-2g5.md
```

至少包括：

```text
Provider
Model
Validation Model vs Default
Samples
Runs
Windows
Coverage
Tokens
Costs
Ledger
Evidence Results
Persistence Results
P0/P1/P2
Medium Sample Status
Public HEAD
Private HEAD
Result
Next Step
```

通过后才能读取 `STEP-2.6-DETAILED.md`。
