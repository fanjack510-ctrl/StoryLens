# Phase 2B First Four Modules

**Status:** Historical Phase 2B engine/module contract.  
**AMENDED BY CHG-20260803-044：** 本文 A–D 描述的是 Phase2B 私有引擎“first-four”契约（含 **storylines**），**不是** V1.2.0 产品 Free 四模块清单。

| 概念 | 模块集合 |
|---|---|
| Phase2B first-four（本文） | overview / structure_stages / chapter_functions / **storylines** |
| V1.2.0 Free four（产品） | overview / **characters_events** / structure / chapter_functions |

V1.2.0 不交付 Storylines；`WB-2.4-FIRST-FOUR-PRODUCT` 对产品路径标记为 **superseded_by_current_free_four_modules**。详见 `release/evidence/whole-book/CHG-20260803-044/WB23_WB24_DISPOSITION.md`。

Out of Phase 2B scope: character arcs, deep character relations, hook recovery, causal chains, full timeline, diagnosis, formal Structure Map page, cross-book search, Story Lab.

## A. book_overview → BookOverviewResultDto

Goal: verifiable whole-book overview (not marketing copy).

Key fields: `logline`, `premise`, `central_question`, `primary_conflict`, `protagonist_asset_id`, `major_storyline_ids`, `structure_summary`, `ending_state`, `evidence_refs`, `confidence`

Rules: partial allowed; key claims need Evidence; unknown/multiple protagonists allowed; no forced single protagonist; no forced single central conflict.

## B. structure_stages → StructureStagesResultDto

Rules: no forced three-act; variable stage count; stages require chapter ranges; turning points need Evidence; “no stable stages identified” allowed; no genre-hardcoded structure templates.

## C. chapter_functions → ChapterFunctionsResultDto

Rules: multiple function tags per chapter; primary/secondary allowed; chapters need not advance main plot; empty/side/flashback chapters may be tagged explicitly; tags from general enums + explanation; each judgment traceable to chapter Evidence.

## D. storylines → StorylinesResultDto

Rules: general types (main/side/relationship/quest, etc.) — not genre-specific; one event may belong to multiple storylines; pause/resume/terminate/incomplete states; bind key events; Evidence covers start/change/end judgments; character lists are not storylines.
