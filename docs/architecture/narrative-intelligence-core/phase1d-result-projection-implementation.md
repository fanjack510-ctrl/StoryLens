# Phase 1D Result Projection Implementation

Change: `CHG-20260723-028`  
Agent: K  
Branch: `feature/narrative-phase1d-result-projection`

## Scope

Read-only projection of whole-book results from existing RunStage / Artifact / Asset / Relation / Evidence / Conflict data.

Does **not**:

- analyze novels or call models
- create Assets / Relations / Conflicts
- switch canonical, confirm, or resolve conflicts
- add DB tables / migrations
- register production Run create

## Primary artifacts

| Path | Role |
|------|------|
| `apps/api/app/narrative_core/services/whole_book_result_projection.py` | `WholeBookResultIndexService` + status + Envelope builders + Pattern inputs |
| `apps/api/app/routers/whole_book_results.py` | Read-only result router (not mounted in `main.py`) |
| `apps/api/tests/test_narrative_phase1d_result_projection.py` | Directed tests |
| `apps/api/app/narrative_core/services/whole_book_stage_plan.py` | Clarified Engine planning alias only |

## Service API

`WholeBookResultIndexService`:

- `get_result_index(run_id)`
- `get_module_result(run_id, module_key, view="canonical"|"candidate")`
- `list_available_modules(run_id)`
- `get_module_status(run_id, module_key)`
- `refresh_projection(run_id)` — clears in-memory cache only

Constraints enforced:

1. Book-scope Run required (`INVALID_RUN_SCOPE` otherwise)
2. Missing Run → typed failure
3. Results bind `run_id` + `book_snapshot_id`
4. Default view = canonical; candidate must be explicit
5. Rejected versions excluded
6. Payload via Module DTOs / empty legal DTOs
7. Evidence as refs / counts only — no full body text

## Reuse

- Phase 1D-P `product_contract` Envelope + Module DTOs + `MODULE_STAGE_DEPENDENCIES`
- Phase 1A RunStage rows
- Phase 1B Asset / Relation / Evidence / Conflict
- Phase 1C stage artifact envelope (optional coverage hint)

## Related docs

- [phase1d-module-status-aggregation.md](./phase1d-module-status-aggregation.md)
- [phase1d-result-api-readonly.md](./phase1d-result-api-readonly.md)
- [phase1d-result-projection-performance.md](./phase1d-result-projection-performance.md)
- [phase1d-result-projection-verification.md](./phase1d-result-projection-verification.md)
