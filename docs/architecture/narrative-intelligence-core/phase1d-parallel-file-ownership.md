# Phase 1D Parallel File Ownership

Branch/worktree isolation for Agents J/K/L after Phase 1D-P contract freeze.

| Agent | Change | Branch | Worktree |
|-------|--------|--------|----------|
| Phase 1D-P | CHG-026 | `feature/narrative-phase1d-product-contract` | `D:\Dstorylens-wt-narrative-phase1d-contract` |
| J (Run UX) | CHG-027 | `feature/narrative-phase1d-run-ux` | `D:\Dstorylens-wt-narrative-run-ux` |
| K (Result projection) | CHG-028 | `feature/narrative-phase1d-result-projection` | `D:\Dstorylens-wt-narrative-result-projection` |
| L (Review / Map) | CHG-029 | `feature/narrative-phase1d-review-map` | `D:\Dstorylens-wt-narrative-review-map` |
| Integration | CHG-030 | `integration/narrative-phase1d` | `D:\Dstorylens-wt-narrative-phase1d-integration` |

Baseline: `44a9dcf864571fb9f27282cefae282bae478540b` (Phase 1C Integration HEAD).  
Machine-readable: [phase1d-parallel-file-ownership.json](./phase1d-parallel-file-ownership.json).

## Phase 1D-P (shared contract owner)

- `apps/api/app/narrative_core/product_contract/*`
- `apps/desktop/src/features/wholeBook/contracts/*`
- Docs listed in Phase 1D-P section of README
- `apps/api/tests/test_narrative_phase1dp_contract.py`
- `release/changes/CHG-20260723-026.json` … `030.json`

## Agent J — Preflight / Run UX

Owns (to be created by J):

- `apps/desktop/src/features/wholeBook/runUx/`

Scope: Preflight page prototype, mode/module selection, progress, pause/resume/retry/cancel.  
**Must not** modify result projection.

## Agent K — Result DTO / Projection

Owns (future / skeleton):

- `apps/api/app/narrative_core/services/whole_book_result_projection.py`
- Result index / module result fixtures / read-only result API skeleton under K’s agreed router paths

**No** Review UI.

## Agent L — Evidence / Review / Map

Owns (to be created by L):

- `apps/desktop/src/features/wholeBook/review/`
- `apps/desktop/src/features/wholeBook/structureMap/`

Scope: Evidence Drawer, review action adapters, Conflict Center prototype, Structure Map projection adapters.  
**No** analysis algorithms.

## Integration

- Cross-contract consistency (FE/BE keys & enums)
- Preflight → Run View → Result Index e2e contract tests
- Evidence → Review → Conflict → Pattern projection wiring checks
- README / Change Registry / integration tests

## Forbidden overlap

- Real whole-book runs / model calls
- `PRO_CAPABILITIES_SHIPPED=true`
- `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=false`
- Migrations / Narrative Asset schema edits / Pattern tables
- `VERSION` bump / Tag / baseline / installers
- push / build / publish
- Editing another agent’s owned paths (see JSON)

All parallel branches **fork from Phase 1D-P final HEAD**.
