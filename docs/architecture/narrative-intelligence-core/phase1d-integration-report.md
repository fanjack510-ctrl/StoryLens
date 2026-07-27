# Phase 1D Integration Report

**Change:** CHG-20260723-030  
**Branch:** `integration/narrative-phase1d`  
**Worktree:** `D:\Dstorylens-wt-narrative-phase1d-integration`  
**Source:** `f79f199ea9dc53b8e92ae661baef3dc62007e905` (Phase 1D-P)  
**VERSION:** 1.0.5  

## Scope

Merge Agent J/K/L, unify public contracts, register read-only Result API, verify product chain.  
**Not in scope:** real whole-book Run create, model calls, real analysis algorithms, Review write routes, formal product navigation.

## Merge order

1. Agent J (`feature/narrative-phase1d-run-ux`) — all commits  
2. Agent K (`feature/narrative-phase1d-result-projection`) — all commits  
3. Agent L (`feature/narrative-phase1d-review-map`) — all commits  

Cherry-picks applied cleanly (no conflicts). Agent worktrees untouched.

## Integration corrections

| Area | Correction |
|------|------------|
| Preflight | Transport DTO `WholeBookPreflightResponseDto` vs PageModel; Mapper owns case/schema checks |
| Run creation | `backend` / `client` / `effective` triad; effective remains false |
| Module↔Stage | `ENGINE_MODULE_PLANNING_STAGES` vs `PRODUCT_MODULE_STAGE_DEPENDENCIES` + auto consistency |
| Result API | `whole_book_results` registered in `main.py` |
| Review write | Adapter kept; **not** registered |
| Structure Map | Consumes `NarrativeProjectionSource` only |

## Safety

- `PRO_CAPABILITIES_SHIPPED=false`
- `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
- `PRODUCTION_DEFAULT_ENGINE_ID=None`
- No Pattern tables / migrations / VERSION bump / push / build / publish

See also: [phase1d-known-limitations.md](./phase1d-known-limitations.md).
