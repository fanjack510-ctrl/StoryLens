# WB-2.2 SCOPE AND IMPLEMENTATION PLAN

CHANGE：CHG-20260802-038  
DATE：2026-08-02  
PRODUCT CODE MODIFIED：**NO**  
REAL PROVIDER CALLS：0  
WB-2.2 IMPLEMENTATION STARTED：**NO**

## Baseline after WB-2.1 verified

| Item | Value |
|---|---|
| Public branch | `integration/1.2.0-after-1.1.2` |
| Public HEAD (planning base) | post CHG-037 verify commit |
| Private HEAD | `d56314483a65454c1ce21778d554f7e8d4d57876` |
| VERSION | 1.2.0 |
| WB-2.1 | verified (MG-WB-2.1 PASSED) |

## WB-2.2 SOURCE FILES（直接证据）

| Path | Lines / note |
|---|---|
| `docs/whole-book/EXECUTION_REGISTRY.json` | 452–466 — step `WB-2.2-CHAPTER-FUNCTIONS` |
| `release/changes/CHG-20260728-019.json` | recovery record (this CHG) |
| `docs/architecture/narrative-intelligence-core/phase2b-first-four-modules.md` | 17–19 — module C rules |
| `docs/architecture/narrative-intelligence-core/phase2br-implementation-plan.md` | ~89 |
| `docs/architecture/narrative-intelligence-core/phase1d-module-result-contracts.md` | 40–54 |
| `apps/api/.../module_spec.py` | 117–138 — `CHAPTER_FUNCTIONS_SPEC` |
| `apps/api/.../module_results.py` | 287–297 — `ChapterFunctionsResultDto` |
| `apps/api/.../whole_book_product_capability_v1.py` | 64–69 — Free planned |
| `apps/desktop/.../wholeBookFreeProductApi.ts` | 119–130 — UI planned |
| `apps/desktop/.../WholeBookFreeProductPage.tsx` | 679–680 — PlannedModulePanel |
| Private `modules/chapter_functions/runner.py` | Lab runner |
| Private `prompt_packs/chapter_functions/` | system.md + manifest |
| `apps/api/.../enums.py` | AssetType `chapter_function` |
| `apps/api/.../constants.py` WHOLE_BOOK_STAGE_CODES_V1 | **no** chapter_functions stage yet |

## Formal definition

```json
{
  "step_id": "WB-2.2-CHAPTER-FUNCTIONS",
  "change_id": "CHG-20260728-019",
  "manual_gate_id": "MG-WB-2.2",
  "title": "Chapter functions",
  "acceptance_level": "L3",
  "depends_on": ["WB-2.1-STRUCTURE-STAGES"],
  "next_step": "WB-2.3-STORYLINES",
  "wb_status": "planned"
}
```

## Answers to required product questions

| # | Question | Answer | Certainty |
|---|---|---|---|
| 1 | Formal name | **WB-2.2-CHAPTER-FUNCTIONS** / title「Chapter functions」/ UI「章节功能」 | PASS |
| 2 | User problem | 理解每一章在全书中的叙事作用（推进、铺垫、转折、空章等），可证据回溯 | INTENT（phase2b） |
| 3 | What is analyzed | Per-chapter **function labels** (multi-tag) + change summary + related storyline/character/hook/payoff refs (Lab DTO) | Lab DTO |
| 4 | Per-chapter vs aggregate | **逐章输出**（DTO 以 `chapter_id`/`chapter_order` 为键）；引擎可按批（max 8 chapters） | PARTIAL |
| 5 | Role in whole book | Yes — narrative function of chapter in book context | INTENT |
| 6 | Label set (开篇/冲突/高潮…) | **示例意图，非产品冻结枚举**。SPEC 允许 empty/side/flashback；具体中文标签集 **UNRESOLVED** | UNRESOLVED |
| 7 | Labels from formal Contract? | Lab DTO 仅 `function_labels: tuple[str,...]`；**无**冻结枚举表 → 示例级 | UNRESOLVED |
| 8 | Multi-function per chapter | **YES** — `multi_function_labels=True` | PASS |
| 9 | Primary/secondary required? | SPEC `primary_secondary_functions=True`；但 DTO **无**独立 primary/secondary 字段，标签混在 `function_labels` → 结构 **UNRESOLVED** | UNRESOLVED |
| 10 | Confidence | Lab DTO **无** confidence；是否加入产品 V2 **UNRESOLVED** | UNRESOLVED |
| 11 | Interval vs per-chapter | **逐章结果**；无章区间聚合输出契约 | PASS（逐章） |
| 12 | Evidence required? | INTENT yes（phase2b）；DTO `evidence_refs` | PARTIAL |
| 13 | Evidence granularity | 文档要求章级可追溯；字符偏移级 V2 cited-claim **未冻结** → **UNRESOLVED** | UNRESOLVED |
| 14 | Depends WB-2.1? | Registry **depends_on** WB-2.1（编排）；是否消费 StructureStagesResultV2 作输入 → **UNRESOLVED** | UNRESOLVED |
| 15 | Depends characters/events? | DTO 有 `character_focus_ids`；是否原生依赖人物模块结果 → **UNRESOLVED**（倾向禁止作 SoT） | UNRESOLVED |
| 16 | Chapter analysis / journey? | **FORBIDDEN as native SoT**（继承合同） | PASS |
| 17 | Free / Pro | **Free** planned → productize；storylines Pro | PASS |
| 18 | Long-book paging | Engine `max_chapters_per_batch=8`；产品分页/虚拟列表 **UNRESOLVED** | UNRESOLVED |
| 19 | Empty / insufficient | SPEC 允许 empty/side/flashback tags；产品 empty-policy 冻结 **ABSENT** | UNRESOLVED |
| 20 | Boundary vs later Pro | storylines / arcs / hooks 属后续 Pro；勿混 insights `ChapterFunctionsResultV1` | PASS |

## WB-2.1 as derived context

**WB-2.1 INPUT ALLOWED：UNRESOLVED**

- 有：depends_on、Lab 顺序 structure → chapter_functions  
- 无：冻结声明「结构 V2 为派生上下文 / 缺失时仍可运行」  
- Freeze 轮必须二选一并写入合同，**禁止自行决定**

若最终允许：原文 Snapshot 仍为事实源；structure 仅派生上下文；structure 缺失不得硬阻塞。

## Inherited mandatory contracts

- Native Immutable Snapshot / Revision  
- No chapter-analysis / journey / aggregate SoT  
- Confirmed no silent overwrite；conflict → new version  
- Exact Evidence；no fuzzy fallback  
- No novel-specific branches  
- Free=4 / Pro=8 planned；no purchase/License UI  
- Do not break StructureStagesResultV2 or v1.1.2 single-chapter  

## SOURCE CONSISTENCY：**INSUFFICIENT**（含 CONFLICT）

见 `CONFLICTING_DOCUMENTS.md`。

## Implementation blockers（编码前）

1. CHG-019 recovery（本轮已建 recovery record）  
2. Canonical contract：Lab V1 DTO vs 需要新 V2（**UNRESOLVED**）  
3. Empty / insufficient policy freeze  
4. DATABASE / Migration decision  
5. Product API path + pagination  
6. Pipeline stage code + provider units  
7. WB-2.1 derived-context decision  

→ **不得授权编码**；下一步必须 **WB-2.2 Pre-Implementation Freeze**。
