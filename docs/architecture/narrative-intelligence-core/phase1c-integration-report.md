# Phase 1C Integration Report

**Change:** CHG-20260723-025  
**Branch:** `integration/narrative-phase1c`  
**Worktree:** `D:\Dstorylens-wt-narrative-phase1c-integration`  
**Source:** `a275e837a392a1d21a11040cc71670548b1160ef` (`feature/narrative-phase1c-contract`)  
**VERSION:** 1.0.5  
**Status:** tested (not ready / not released)

## Merge order

1. Agent G `feature/narrative-phase1c-engine` (4 commits cherry-picked)
2. Agent H `feature/narrative-phase1c-capability-backend` (3 commits cherry-picked)
3. Agent I `feature/narrative-phase1c-capability-frontend` (3 commits cherry-picked)
4. Integration corrections (this change)

No merge of `release/1.0.5`. No rebase of Agent branches. No push.

## Integration corrections

| Topic | Resolution |
|-------|------------|
| `relation_writer` | First-class field on `WholeBookStageContext`; no longer via `extra` |
| Stage Artifact | Frozen `WholeBookStageArtifactEnvelope` / `artifact_type=whole_book_stage_result` on existing `analysis_artifacts` |
| Metadata | `whole_book_analysis`: `preview_visible=true`, `availability=preview`, `shipped=false` |
| Mode deny | `CAPABILITY_MODE_NOT_SUPPORTED` (unknown key still `CAPABILITY_UNKNOWN`) |
| Preflight | `POST /api/v1/books/{book_id}/whole-book-runs/preflight` read-only |
| Request chain | Test helper: Guard → backend Decision → Request → Engine.validate / stage plan |
| Frontend | Backend payload fixtures; mode presentation; preview visible ≠ startable |

## Hard flags unchanged

- `PRO_CAPABILITIES_SHIPPED=false`
- `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
- `PRODUCTION_DEFAULT_ENGINE_ID=None`
- No production Engine registration
- No model calls / real whole-book algorithms

## Related docs

- [phase1c-engine-capability-e2e.md](./phase1c-engine-capability-e2e.md)
- [phase1c-capability-api-verification.md](./phase1c-capability-api-verification.md)
- [phase1c-whole-book-preflight.md](./phase1c-whole-book-preflight.md)
- [phase1c-mock-production-isolation.md](./phase1c-mock-production-isolation.md)
- [phase1c-known-limitations.md](./phase1c-known-limitations.md)
