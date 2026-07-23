# Phase 1B Parallel File Ownership

Machine twin: [phase1b-parallel-file-ownership.json](./phase1b-parallel-file-ownership.json)

## Baseline

| Item | Value |
|------|-------|
| Source commit | `fc25a984f243d641d91c11d887d07af8b3625fdd` |
| Phase 1B-P branch | `feature/narrative-phase1b-contract` |
| Phase 1B-P worktree | `D:\Dstorylens-wt-narrative-phase1b-contract` |
| VERSION | `1.0.5` |

## Roles

### Phase 1B-P (this Change)

Shared ORM skeleton, enums, errors, Protocols/DTOs, migration IDs 006–010 DDL skeleton, ownership docs, Change pre-registration, contract tests.

### Agent D — Entity / Alias

Branch: `feature/narrative-phase1b-entities`  
Worktree: `D:\Dstorylens-wt-narrative-entities`  
Owns: Entity/Alias repository + service, migration **006** refinements, Entity tests/docs.  
**Must not** alter `models.py` table structure.

### Agent E — Asset / Version / Evidence

Branch: `feature/narrative-phase1b-assets`  
Worktree: `D:\Dstorylens-wt-narrative-assets`  
Owns: Asset services, migrations **007–008**, evidence validation via Snapshot gateway, Asset tests/docs.

### Agent F — Relation / Conflict

Branch: `feature/narrative-phase1b-relations`  
Worktree: `D:\Dstorylens-wt-narrative-relations`  
Owns: Relation + Conflict services, migrations **009–010**, Relation evidence validation, Conflict tests/docs.

### Integration

Branch: `integration/narrative-phase1b`  
Worktree: `D:\Dstorylens-wt-narrative-phase1b-integration`  
Owns: 006–010 co-verification, Entity→Asset→Relation E2E, canonical uniqueness, Lock/Conflict, registry/README cross-module tests.

## Shared high-risk files

| Path | Rule |
|------|------|
| `apps/api/app/db/models.py` | Frozen after Phase 1B-P — Agents D/E/F read-only for schema |
| `apps/api/app/db/session.py` | Integration-only unless coordinated |
| `apps/api/app/narrative_core/migrations/runner.py` | Line-range: D=006, E=007–008, F=009–010 |
| `apps/api/app/narrative_core/enums.py` / `errors.py` | Additive only with Integration review |
| `release/unreleased.json` | Attach own Change only |
| `docs/architecture/narrative-intelligence-core/README.md` | Integration merges index |

## Downstream branch rule

All Agent D/E/F/Integration branches **must** fork from Phase 1B-P final HEAD (not from Agent A/B/C branches, not from `v1.0.5` tag alone).
