# FOUR_MODULE_RUN_AUDIT — CHG-20260803-045

## Product modules
1. overview  
2. characters_events  
3. structure  
4. chapter_functions  

## Answers

| # | Question | Answer | Notes |
|---|---|---|---|
| 1 | Same Snapshot / Revision? | **YES**（fixture create） | `create_fixture_free_whole_book_analysis_v1` → one `create_or_reuse_book_snapshot_v1` then one run |
| 2 | Same Run? | **YES**（fixture pipeline） | `execute_fixture_minimal_pipeline_v1` 单 `run_id` 串行 |
| 3 | Unified stage state? | **YES / PARTIAL** | `WholeBookRunStageRow` + `current_stage_code`；characters_events 无独立 synthesize stage |
| 4 | Independent per-module runs? | **NO** on Free fixture path | 不存在四模块各自 create-run；Lab/Mock 另路径 DEV/env 门禁 |
| 5 | project_result waits all required? | **PARTIAL** | CF `finalize_run=True` 收尾；overview/structure 可 `finalize_run=False`；缺“四模块必需 stage 齐备才 completed”的统一断言测 |
| 6 | partial/insufficient → final run | **PARTIAL** | 模块级 result_status + fixture modes；跨模块组合矩阵不全 |
| 7 | One module fail blocks others read? | **PARTIAL / designed soft** | structure soft-fail 注释允许后续 CF；需正式页验证失败模块不拖垮其他读取 |
| 8 | Resume only unfinished units? | **PARTIAL** | orchestrator + WB-1.8/2.1/2.2 unit tests；缺“overview 完成 + CF 半批”跨阶段 Resume 正式测 |
| 9 | Completed modules re-called? | **0 intended** | checkpoint reuse / completed short-circuit in pipeline L53–65；需 E2E 证明 |
| 10 | Assets re-created? | **0 intended** | materialize + confirmed no-overwrite；需跨模块 Resume 证明 |
| 11 | Contract versions identifiable? | **YES** | Overview/Structure V2/CF V2 checkpoints + engine/prompt ids |
| 12 | Survive refresh/reentry? | **PARTIAL** | DB 持久化 YES；UI restore PARTIAL |

## Status matrix (fixture Free run)

| Module | Stage source | Same run | Readable after complete | Contract |
|---|---|---|---|---|
| overview | `synthesize_overview` | YES | YES | overview contract |
| characters_events | extraction + materialization assets | YES | YES（assets/entities API） | entity/event assets |
| structure | `synthesize_structure_stages` | YES | YES | StructureStagesResultV2 |
| chapter_functions | `synthesize_chapter_functions` | YES | YES | ChapterFunctionsResultV2 |

## Gaps (Wave 1)
1. 跨四模块同一 Run 的正式自动化（非仅 fixture helper 单测）  
2. characters_events 作为产品模块 vs pipeline stage 命名一致性文档化（不改产品能力）  
3. 单模块失败时其他模块可读的正式页断言  
4. mid-pipeline Resume 不重跑已完成 overview/structure/CF batches  

## Non-gaps
- 不为 Storylines 增加模块  
- 不重写已通过 WB-2.1/2.2 模块契约  
