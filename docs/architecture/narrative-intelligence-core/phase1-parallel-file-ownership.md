# Phase 1 Parallel File Ownership

Machine-readable twin: `phase1-parallel-file-ownership.json`.

## Rules

1. Prefer not to edit another Agent’s exclusive paths.  
2. `apps/api/app/db/models.py` is **frozen after Phase 1P** for Agents A/B/C — schema changes go through Integration.  
3. `apps/api/app/db/session.py` create_db hook is frozen; migration bodies live under `narrative_core/migrations/`.  
4. Shared read-only: contracts, enums, stage matrix, hash_canon, Phase 1P docs.  
5. Merge order on conflict: Integration → prefer Agent A schema facts → Agent B run/stage → Agent C docs/frontend drafts.

## Phase 1P (this Change) — completed ownership

Creates and owns the initial freeze of:

- `apps/api/app/narrative_core/**` (enums, errors, hash_canon, stage_transitions, contracts, migrations)  
- Shared ORM skeleton in `apps/api/app/db/models.py`  
- `create_db` hook in `apps/api/app/db/session.py`  
- Contract docs under `docs/architecture/narrative-intelligence-core/phase1-*`  
- Change pre-registration `release/changes/CHG-20260723-011` … `015`  
- Local tests `apps/api/tests/test_narrative_phase1p_contract.py`

## Agent A exclusive (implement next)

- `apps/api/app/narrative_core/services/hash_backfill.py` (create)  
- `apps/api/app/narrative_core/services/snapshot_repository.py` (create)  
- `apps/api/app/narrative_core/services/snapshot_service.py` (create)  
- `apps/api/app/narrative_core/services/migration_ledger.py` (create)  
- `apps/api/tests/test_narrative_snapshot_*.py` (create)  
- `docs/architecture/narrative-intelligence-core/phase1a-snapshot.md` (create)  
- May refine DDL **inside** `runner.py` functions 001–003 only if Integration agrees; prefer service-layer work

## Agent B exclusive

- `apps/api/app/narrative_core/services/run_scope_service.py` (create)  
- `apps/api/app/narrative_core/services/run_stage_repository.py` (create)  
- `apps/api/app/narrative_core/services/run_stage_service.py` (create)  
- `apps/api/tests/test_narrative_run_stage_*.py` (create)  
- `docs/architecture/narrative-intelligence-core/phase1a-runstage.md` (create)  
- Consumes `SnapshotValidationGateway` — **do not** duplicate snapshot SQL  

## Agent C exclusive

- `docs/architecture/narrative-intelligence-core/phase0b-pattern-map-readiness.md` (create)  
- `apps/desktop/src/features/narrativePattern/**` (create drafts/mocks only)  
- Must not modify `apps/api/app/db/models.py` or migrations  

## Integration exclusive

- Merge conflict resolution  
- `apps/api/tests/test_narrative_phase1a_integration.py` (create)  
- Cross-module fixtures  
- Final Change commit attachments for CHG-015  

## Remaining shared-write risks

| File | Risk | Mitigation |
|------|------|------------|
| `apps/api/app/db/models.py` | Accidental column adds | Read-only for A/B/C after 1P |
| `apps/api/app/db/session.py` | Extra create_db hooks | Frozen; only Integration |
| `apps/api/app/narrative_core/migrations/runner.py` | A and B both edit | A: 001–003; B: 004–005; avoid touching the other block |
| `release/unreleased.json` | Concurrent Change edits | Each Agent updates only own CHG file; Integration syncs pool |
| `docs/architecture/README.md` | Index collisions | Append-only rows |

## Planned worktrees / branches

| Role | Branch | Worktree |
|------|--------|----------|
| Agent A | `feature/narrative-phase1a-snapshot` | `D:\Dstorylens-wt-narrative-snapshot` |
| Agent B | `feature/narrative-phase1a-runstage` | `D:\Dstorylens-wt-narrative-runstage` |
| Agent C | `feature/narrative-pattern-readiness` | `D:\Dstorylens-wt-pattern-audit` |
| Integration | `integration/narrative-phase1a` | `D:\Dstorylens-wt-narrative-integration` |
