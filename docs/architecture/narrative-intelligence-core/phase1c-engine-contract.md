# Phase 1C Engine Contract

Frozen `WholeBookAnalysisEngine` Protocol (Phase 1C-P). Agent G implements; Phase 1C-P owns the interface.

## Engine surface

| Method | Purpose |
|--------|---------|
| `engine_id` / `engine_version` | Stable identity for registry |
| `supported_modes()` | `whole_book_native`, `whole_book_enhanced` |
| `supported_modules()` | `WholeBookModuleKey` catalog |
| `validate_request` | DTO shape + pre-evaluated `CapabilityDecision` |
| `build_stage_plan` | Ordered `WholeBookStageDefinition` list |
| `execute_stage` / `resume_stage` / `cancel_stage` | Stage lifecycle |
| `health_check` | Registry probe |

## Hard boundaries

- Engine **must not** parse License objects — only `CapabilityDecision`.
- Engine **must not** accept full novel body in DTOs.
- No real model calls in Phase 1C-P (`MockWholeBookAnalysisEngine` only).
- `POST /whole-book-runs` **disabled** until Integration (CHG-025).

## Files

- `apps/api/app/narrative_core/contracts/engine.py`
- `apps/api/app/narrative_core/services/mock_whole_book_engine.py`
- `apps/api/app/narrative_core/services/whole_book_engine_registry.py`

See [phase1c-stage-contract.md](./phase1c-stage-contract.md), [phase1c-engine-asset-boundary.md](./phase1c-engine-asset-boundary.md).
