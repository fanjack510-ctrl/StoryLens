# Phase 1D Module Status Aggregation

## Dual mapping contract (unified clarity)

Two mappings remain **intentionally distinct** — not duplicated under unclear names:

| Name | Location | Role |
|------|----------|------|
| **Engine planning mapping** | `MODULE_TO_STAGES` / `ENGINE_MODULE_PLANNING_STAGES` in `whole_book_stage_plan.py` | Which primary *analysis* stages to schedule when building a plan (+ scaffold + DAG close) |
| **Product result dependency mapping** | `MODULE_STAGE_DEPENDENCIES` / `PRODUCT_MODULE_STAGE_DEPENDENCIES` in `product_contract.keys` | Which stages feed module **result status** / Envelope `source_stage_keys` |

Result projection **must** use the product dependency mapping.  
Engine plan builders **must** use the engine planning mapping.

They are many-to-many in both directions:

- one Module spans multiple Stages
- one Stage supports multiple Modules

There is **no** 1:1 UI-module ↔ stage key mapping.

## Status enum

`not_requested` · `pending` · `running` · `partial` · `completed` · `failed` · `stale` · `blocked`

## Aggregation rules (`aggregate_module_status`)

Inputs:

- `requested_modules` (from Run `validated_output` / checkpoint / inferred planning stages)
- RunStage statuses for product dependency stages
- usable output (Asset/Relation/Artifact coverage)
- stale flags (Asset/Relation lifecycle or checkpoint)
- open **blocking** Conflict presence

Rules:

1. Module not in requested set → `not_requested`
2. Any dependency stage `running` → `running`
3. Any dependency `failed`:
   - with usable output → `partial` (do not drop existing results)
   - without usable output → `failed`
4. All dependency stages completed/skipped → `completed`, or `stale` if stale
5. Incomplete + usable output → `partial`
6. Open **blocking** Conflict while incomplete → `blocked`
7. Warning/info Conflict ≠ blocked
8. `stale` is never equated to `failed`

## Requested module resolution

Without a dedicated DB column:

1. `AnalysisRun.validated_output` / `raw_output` JSON `requested_modules`
2. Stage `checkpoint_json` `requested_modules`
3. Infer from Engine planning stages present on the Run
