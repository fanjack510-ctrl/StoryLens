# ADR-003：统一叙事资产（Entity / Asset / Relation / Evidence）

- **Status:** Accepted (STEP 1.3)
- **Change:** CHG-20260725-003
- **Date:** 2026-07-25

## Context

十一项整书产品能力若各自抽人、各自存 JSON，将产生矛盾主角、分裂故事线与无法共享 Evidence。Phase 1B 已建立 ORM 骨架；需冻结长期类型集合与生命周期，同时允许当前 Enum 命名逐步演进。

## Decision

1. **十一模块共用同一叙事底座**（Entity / Asset / Relation / Evidence + Snapshot / Run）。  
2. **禁止**每页独立事实源、独立业务库、互不关联大 JSON、重复无证抽取。  
3. 长期实体 / 资产 / 关系目标集合见总架构文档第 7 节；**本 ADR 不修改 Enum**。  
4. 生命周期目标：`candidate → validated → accepted|rejected`（+ lock / superseded / stale）。  
5. Current `ReviewStatus`（`candidate|confirmed|corrected|rejected`）继续有效；映射到目标语义时，`confirmed/corrected ≈ accepted`。  
6. 正式资产与关系必须可追溯来源 Run 与 Evidence。  

### Current Enum 摘要（不得在 STEP 1.3 改动）

- **EntityType：** character, location, organization, faction, object, concept, timeline_entity, unknown  
- **AssetType：** event, goal, conflict, choice, consequence, question, hook, clue, foreshadowing, misdirection, reveal, partial_payoff, final_payoff, reversal, storyline, structure_stage, chapter_function, character_arc_stage, diagnosis_input  
- **RelationType：** causes, enables, blocks, escalates, resolves, pays_off, foreshadows, reveals, contradicts, belongs_to, advances, changes_relationship, precedes, parallels  

缺失的目标类型记入路线图后续 Step，不在本阶段补齐。

## Consequences

- STEP 2 Overview 复用现有资产表，不新建 Overview 专用事实库  
- 后续扩展类型走 Migration + Integration 独占 Enum 变更  
- Lab 模块结果须经 Candidate 校验才能成为正式资产  

## Related Steps

STEP 2（最小 Entity/Asset/Evidence + Overview）；STEP 3（统一事实底座）；STEP 4–7（结构/人物/钩子等产品化）。
