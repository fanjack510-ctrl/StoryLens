# MANUAL GATE — MG-WB-0.2

MANUAL GATE：  
MG-WB-0.2

对应 Step：  
WB-0.2-DATA-CONTRACTS

对应 Change：  
CHG-20260728-003

验收等级：  
L1

验收目的：  
确认原生全书分析 V1 数据对象、字段、Wire Contract、Evidence、Confirmed Asset 保护和 Public/Private 边界已经冻结。

验收环境：  
文档、JSON Schema、自动测试结果

真实 Provider：  
NO

Provider调用：  
0

正式数据库写入：  
NO

Migration：  
NO

Build：  
NO

用户需要检查：

1. Contract Version 正确；
2. Snapshot / Run / Window 身份链完整；
3. Native 与 Enhanced 规则正确；
4. Evidence 使用 Snapshot Paragraph 精确定位；
5. locator 失败不会模糊冒充；
6. Candidate / Confirmed 状态清楚；
7. Confirmed 不允许静默覆盖；
8. Conflict 合同完整；
9. Overview 9 个 claim_key 正确；
10. available claim 必须有 Evidence；
11. Fixture / Formal 明确区分；
12. Public / Private Wire Schema Hash 相同；
13. Persistence Mapping 没有重复建模；
14. WB-0.4 Migration Delta 明确；
15. 没有启用产品入口；
16. 没有真实 Provider；
17. 没有正式数据库写入。

PASS格式：

```
MG-WB-0.2：
PASS
CHG-20260728-003：
verified
允许进入：
WB-0.3-CAPABILITY-COST
```

BLOCKED格式：

```
MG-WB-0.2：
BLOCKED
原因：
<具体契约问题>
允许进入WB-0.3：
NO
```

当前自动实现状态：等待人工验收（自动侧 `tested` / Manual Gate `ready`）。  
在用户明确 `MG-WB-0.2 PASS` 之前，不得标记 `verified`，不得开始 WB-0.3。
