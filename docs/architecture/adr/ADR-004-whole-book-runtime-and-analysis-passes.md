# ADR-004：整书运行编排与 5-Pass / 10-Stage

- **Status:** Accepted (STEP 1.3)
- **Change:** CHG-20260725-003
- **Date:** 2026-07-25

## Context

产品需要可恢复、可计费、可重试的整书运行。历史上同时存在：

- 运行协议：`WholeBookStageKey`（10 stages）  
- 算法叙述：5-Pass  

二者若被当成互斥架构，会导致删除 stage 或重复造运行框架。

## Decision

1. **保留并继续使用当前 10-stage 运行协议**；不得删除。  
2. **5-Pass 是分析算法阶段划分**，映射到 stage / 模块，而不是替换 stage 表。  
3. 生产调用链（Target）以 Public Orchestrator 为中心：License → Snapshot → Run/Stage → Window → Private Candidate → Public Materialize → Checkpoint → Projection。  
4. 同一窗口的 Materialize / Evidence / Usage / Checkpoint / 状态版本应尽量同事务（实现细节 STEP 2.1）。  
5. Book 级全局叙事状态是**可恢复运行状态**，非正式事实唯一来源。  
6. 正式 `POST /api/v1/books/{book_id}/whole-book-runs` 在 STEP 2 前保持禁用策略，由后续 Step 显式开启。  

### Pass → Stage 映射框架

| Pass | 焦点 | 主要 Stage Keys |
|------|------|-----------------|
| 0 | 快照与前检 | `build_fulltext_index` + preflight |
| 1 | 事实与实体 | `resolve_entities` |
| 2 | 动态图谱 | `analyze_hooks`, `analyze_causality_timeline` |
| 3 | 全局模型 | `analyze_structure`, `analyze_storylines`, `analyze_characters` |
| 4 | 综合与复核 | `generate_diagnostics`, `verify_evidence`, `persist_narrative_assets` |
| 5 | 整书旅程 | **尚无独立 stage（STEP 7）** |

## Consequences

- Mock / Lab orchestrator 可继续用于验证，但不得称为生产 Orchestrator 已完成  
- STEP 2 可只激活 Overview 所需子集 stage / 模块，而不实现全部 11 模块  

## Related Steps

STEP 2.0–2.x（原生 Overview 运行）；STEP 2.1（事务与 Checkpoint 细化）。
