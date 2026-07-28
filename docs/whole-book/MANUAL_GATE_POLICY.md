# Whole-Book Manual Gate Policy

## Gate count

MANUAL GATES: **37**  
STEPS WITHOUT MANUAL GATE: **0**  
IDs: `MG-WB-0.1` … `MG-WB-6.5` (1:1 with Step IDs)

## Required template fields

Every Manual Gate document must include:

```text
MANUAL GATE：
对应 Step：
对应 Change：
验收等级：
验收目的：
验收环境：
是否真实 Provider：
预计调用数：
最大调用数：
预计 Token：
费用上限：
正式数据库写入：
用户操作：
预期结果：
禁止出现：
PASS 标准：
BLOCKED 标准：
通过后允许进入：
失败后回到：
Evidence：
```

Evidence path: `release/evidence/whole-book/<STEP-ID>/MANUAL_GATE.md`

## Acceptance levels

### L1｜零费用结构验收

Docs, contracts, DTO, Migration, Snapshot, Window, state machine, Evidence structure.  
Provider=0 · formal DB=0 · build=0

### L2｜源码运行态验收

API, dev pages, progress, evidence deep-link, pause/resume, confirm.  
Source run · isolated DB · Provider=0 · no Installer build

### L3｜受控真实算法验收

Entity/event/structure/storyline/arc/hooks/causality/timeline/overview/whole-book RJ.  
Before start freeze: Sample ID, novel scope, chapters, word count, Provider, model, max calls, max tokens, cost cap, retry rules, stop conditions.  
Without user approval: REAL PROVIDER CALLS = 0

### L4｜安装版验收

Only `1.2.0-rc.x` and `1.2.0 Stable`. Do not build Installer per feature step.

## Status authority

| Actor | May set |
|---|---|
| Cursor | implementing, tested, manual verification |
| Cursor automation ceiling | tested |
| User only | verified, integrated |

Cursor must never mark `verified` without an explicit user PASS (e.g. `MG-WB-X.X PASS`).

## Dependency rule

No dependent Step may start while its prerequisite Manual Gate is not PASS.

## PASS / BLOCKED reply formats

```text
MG-WB-X.X：
PASS
CHG-…：
verified
允许进入：
<next step>
```

```text
MG-WB-X.X：
BLOCKED
原因：
<specific issue>
允许进入下一步：
NO
```
