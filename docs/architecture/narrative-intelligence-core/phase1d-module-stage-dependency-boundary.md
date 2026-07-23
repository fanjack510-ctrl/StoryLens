# Phase 1D Module / Stage Dependency Boundary

Two intentional mappings — **do not collapse**:

## A. Engine Planning — `ENGINE_MODULE_PLANNING_STAGES`

- Location: `apps/api/app/narrative_core/services/whole_book_stage_plan.py`
- Deprecated alias: `MODULE_TO_STAGES`
- Purpose: seed analysis stages when building an execution plan  
- Scaffold + DAG close applied by `build_whole_book_stage_plan`

## B. Product Result Dependencies — `PRODUCT_MODULE_STAGE_DEPENDENCIES`

- Location: `apps/api/app/narrative_core/product_contract/keys.py`
- Deprecated alias: `MODULE_STAGE_DEPENDENCIES`
- Purpose: decide when a **result module** is pending/running/partial/completed/failed/stale/blocked  
- Frontend mirrors this table only (no third Engine Planning table)

## Consistency rule

Product Result Dependencies **must be a subset** of Engine Planning Closure  
(for each module, stages that `build_whole_book_stage_plan(requested_modules=(module,))` would schedule).

Auto check: `app.narrative_core.services.module_stage_mapping_consistency`.

## Why they differ

Planning seeds minimize primary analysis stages and rely on scaffold+DAG for closure.  
Product dependencies list stages that **gate result viewability** (often broader explicit deps, still within closure).
