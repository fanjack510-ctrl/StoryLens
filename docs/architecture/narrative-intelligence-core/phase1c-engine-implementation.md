# Phase 1C Agent G — Engine Implementation

**Change:** CHG-20260723-022  
**Branch:** `feature/narrative-phase1c-engine`  
**Worktree:** `D:\Dstorylens-wt-narrative-engine`  
**Baseline:** `a275e837a392a1d21a11040cc71670548b1160ef` (Phase 1C-P)

## Scope

Implements the public WholeBook analysis engine skeleton against frozen Phase 1C-P Protocols:

| Component | Path |
|-----------|------|
| Registry / Factory | `apps/api/app/narrative_core/services/whole_book_engine_registry.py` |
| Mock Engine | `apps/api/app/narrative_core/services/mock_whole_book_engine.py` |
| Stage plan builder | `apps/api/app/narrative_core/services/whole_book_stage_plan.py` |
| I/O adapters | `apps/api/app/narrative_core/services/whole_book_engine_adapters.py` |
| Stage orchestrator | `apps/api/app/narrative_core/services/whole_book_stage_orchestrator.py` |
| Tests | `apps/api/tests/test_narrative_phase1c_engine.py` |

## Registry / Factory

- `InMemoryWholeBookEngineRegistry`: `register` / `unregister` / `get` / `list_engines` / `resolve_for_mode` / `health_check_all` (+ Protocol aliases `register_engine` / `get_engine`).
- Duplicate `engine_id` with a different instance fails; same instance is idempotent.
- Missing engine → `WHOLE_BOOK_ENGINE_NOT_FOUND`.
- Does **not** read the database or License objects; Capability decisions stay external.
- `PRODUCTION_DEFAULT_ENGINE_ID = None` — production must not auto-register a real private engine.
- `DefaultWholeBookEngineFactory` creates Mock only; `production_mode=True` refuses Mock for whole-book runs.

## Request validation

`MockWholeBookAnalysisEngine.validate_request` enforces:

1. Shape via frozen `validate_request_shape`
2. Positive `run_id`
3. COMPLETED snapshot belonging to the same book (when SnapshotReader wired)
4. Run / Snapshot consistency (when RunBindingResolver wired)
5. `native` / `enhanced` modes only
6. Supported `requested_modules`
7. `capability_context.allowed` and `capability_key=whole_book_analysis`
8. Non-empty `configuration_fingerprint` when adapters are wired
9. No full novel body fields in request envelopes
10. Enhanced missing chapter assets → degrade flag, not hard fail

## Stage plan

Uses frozen 10-stage catalog. Supports stable order, required scaffold retention, module trim, dependency closure, and cycle detection. Converts definitions to `AnalysisRunStage` keys without renaming stages.

## Out of scope

Real model calls, prompts, live `POST /whole-book-runs`, Capability/License/Quota services, frontend, DB schema, VERSION bump.
