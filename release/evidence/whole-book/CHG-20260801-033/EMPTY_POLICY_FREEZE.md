# EMPTY_POLICY_FREEZE

**Status:** FROZEN for WB-2.1 implementation  
**Source:** Protected WIP empty-policy + Lab StructureStagesResultV2 (CHG-20260725-001)  
**Novel-specific thresholds:** FORBIDDEN

## 1. Legal completed non-empty result

When server-frozen `expected_coverage_scope != insufficient`:

| Rule | Freeze |
|---|---|
| `stages` count | **≥ 1** |
| Forced stage count / 3-act | **Forbidden** (variable stage count) |
| Each stage required | `local_ref`/`stage_key`, title, summary claim (observed\|inferred with non-empty value + ≥1 catalog citation), start_boundary + end_boundary each with ≥1 citation |
| Turning points | **Optional**; `turning_points=[]` allowed even when stages non-empty |
| Each TP when present | title/description claims with citations; related_stage_refs must resolve |
| `coverage_scope` | **Must equal** server-frozen expected scope exactly |
| observed vs inferred | Claim status wire values; observed/inferred require value+citations; `not_observed` only where field policy allows absence |

## 2. Legal empty result

Allowed **only** when:

```text
coverage_scope = insufficient
stages = []
turning_points = []
```

AND server binding has `permits_empty_observation=true` / `expected_coverage_scope=insufficient`  
(i.e. `can_identify_local_stages=false` — no selected chapters/paragraphs units).

Capability true + empty stages → **illegal** (repair once, then fail-closed).

### Deterministic reason / failure codes (IMPLEMENTED in WIP/Private)

| Code | Meaning |
|---|---|
| `STRUCTURE_COVERAGE_SCOPE_BINDING_MISMATCH` | Actual scope ≠ frozen expected; or stages present when empty-only insufficient binding |
| `STRUCTURE_REQUIRED_STAGE_MISSING` | Observation required but `stage_count < 1` |
| `STRUCTURE_EMPTY_RESULT_AFTER_REPAIR` | Empty/binding failure persists after max-1 repair |
| `STRUCTURE_CONTRACT_FAILURE` | Generic contract failure envelope |
| `STRUCTURE_STAGE_SUMMARY_CITATION_EMPTY` | Stage summary missing citations |
| `STRUCTURE_STAGE_START_BOUNDARY_MISSING` / `STRUCTURE_STAGE_END_BOUNDARY_MISSING` | Boundary missing |
| `TURNING_POINT_CITATION_EMPTY` | TP citation missing |
| `STRUCTURE_STAGE_RANGE_OVERLAP` | Overlapping ranges fail-closed |
| `STRUCTURE_COVERAGE_SCOPE_INVALID` | e.g. full_selected_range with `RESOURCE_LIMIT_TRUNCATED` |
| `STRUCTURE_LOCAL_REF_DUPLICATE` / `STRUCTURE_LOCAL_REF_UNKNOWN` | Ref integrity |

### Suggested product-facing empty reasons (NOT IMPLEMENTED — UI mapping only)

Do **not** claim these exist in engine today. Optional UI aliases mapped from binding/capabilities:

| Suggested UI code | Maps from |
|---|---|
| `INSUFFICIENT_TEXT_VOLUME` | `can_identify_local_stages=false` (no units) |
| `INSUFFICIENT_CHAPTER_COVERAGE` | UI label for same / selection empty — **not a Private code** |
| `PROVIDER_OUTPUT_UNRECOVERABLE` | `STRUCTURE_EMPTY_RESULT_AFTER_REPAIR` |

Frozen engine SoT remains the **STRUCTURE_*** codes above.

## 3. Prohibited behaviors

1. Force three-act / genre templates  
2. Invent stages to satisfy non-empty when binding is insufficient  
3. Invent stages when observation required but evidence absent (must fail-closed after repair)  
4. Fuzzy Evidence / wrapper `evidence_map` / non-catalog citations  
5. Fill from chapter-analysis, reader journey, or Aggregate Insights  
6. Silent overwrite of confirmed Narrative Assets  
7. Per-novel keywords, chapter-count hardcodes, or book-title special cases  
8. Confirmed product result without Evidence on observed/inferred claims and boundaries  

## 4. Run/module outcome mapping

| Outcome | Freeze |
|---|---|
| Legal insufficient empty | Structure unit/stage **completed**; result payload present with `coverage_scope=insufficient` |
| Illegal empty after repair | Structure unit/stage **failed** (`STRUCTURE_EMPTY_RESULT_AFTER_REPAIR`); do not persist confirmed assets |
| Cancel | No further provider units; no new assets |
