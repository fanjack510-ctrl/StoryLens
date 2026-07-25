# ADR-005：长文本索引策略（SQLite + FTS5）

- **Status:** Accepted (STEP 1.3)
- **Change:** CHG-20260725-003
- **Date:** 2026-07-25

## Context

整书 Evidence 定位与关键词检索需要本地、可安装、与单库原则一致的方案。引入 Neo4j 或独立向量库会增加运维与第二持久化风险，超出当前阶段边界（见 AGENTS.md）。

## Decision

```text
StoryLens 长期采用：
SQLite + FTS5 + 普通关系表查询
```

范围控制：

- STEP 1.3：**只冻结决策**  
- STEP 2：**不强制**实现 FTS5  
- STEP 3.4：实现或产品化基础全文索引  
- **暂不**引入 Neo4j  
- **暂不**引入向量数据库  

## Reasons

- 与单一业务 SQLite 一致  
- 安装简单、本地优先  
- 适合关键词、段落与 Evidence 定位  
- 关系图可由关系表与递归查询承担  
- 避免额外数据库运维复杂度  

## Limitations

- FTS5 不是语义向量检索  
- 超长书性能需要基准测试  
- 若需求变化，必须通过**新 ADR** 重新评估；禁止单个功能临时引入第二数据库  

## Related Steps

STEP 2（可不实现 FTS5）；STEP 3.4（基础全文索引产品化）。
