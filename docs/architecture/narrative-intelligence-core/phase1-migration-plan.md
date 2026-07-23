# Phase 1 Migration Plan (frozen IDs)

**Baseline:** 1.0.5  
**Checksum input:** SHA-256 of each migration’s frozen SQL body in `apps/api/app/narrative_core/migrations/runner.py` (`SQL_001`…`SQL_005`), normalized with CRLF→LF.

## Order

| # | migration_id | Owner | Precondition | Effect |
|---|--------------|-------|--------------|--------|
| 0 | `baseline_1_0_5` | Phase 1P / Agent A ledger | schema_migrations exists | Marker row only |
| 1 | `20260723_001_schema_migrations` | Agent A | none | Create `schema_migrations` |
| 2 | `20260723_002_content_hashes` | Agent A | `chapters`, `paragraphs` exist | Add nullable `content_hash` + indexes |
| 3 | `20260723_003_book_snapshots` | Agent A | `books`, `chapters` exist | Create snapshot tables |
| 4 | `20260723_004_analysis_run_scope` | Agent B | `analysis_runs`, `book_snapshots` | Add nullable scope columns |
| 5 | `20260723_005_analysis_run_stages` | Agent B | `analysis_runs`, `analysis_artifacts` | Create `analysis_run_stages` |

**Do not renumber.** Integration may only fix SQL bugs while keeping the same `migration_id`.

## Idempotency

- Column/table existence checks before DDL  
- Re-apply records checksum; mismatch → `MIGRATION_CHECKSUM_MISMATCH`  
- Safe to call `apply_narrative_phase1p_migrations` twice  

## Entry point

`create_db()` in `apps/api/app/db/session.py`:

1. Legacy `migrate_phase_*`  
2. `Base.metadata.create_all`  
3. `apply_narrative_phase1p_migrations(engine)`  

## baseline_1_0_5 rules

- Written once with fixed checksum source string  
- Means: DB is evolving from product 1.0.5, not a foreign schema  
- Does not replace per-migration rows  

## Agent implementation boundaries

- Agent A may enrich ledger service / backfill / snapshot builders **without** changing migration_id strings  
- Agent B may implement scope validators / stage services **without** changing migration_id strings  
- If DDL must change after apply in the wild, Integration owns a **new** migration_id (not in 1P set)
