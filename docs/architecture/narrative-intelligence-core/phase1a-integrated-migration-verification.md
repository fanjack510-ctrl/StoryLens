# Phase 1A Integrated Migration Verification

## Order (frozen, not renumbered)

1. `20260723_001_schema_migrations`
2. `20260723_002_content_hashes`
3. `20260723_003_book_snapshots` — **revised pre-release** to add nullable `error_code`, `error_message`
4. `20260723_004_analysis_run_scope`
5. `20260723_005_analysis_run_stages`

Plus ledger marker `baseline_1_0_5`.

## Guarantees verified

| Property | Result |
|----------|--------|
| migration_id unique | yes |
| runner order unique | yes (`apply_narrative_phase1p_migrations`) |
| checksum stable (SHA-256 of SQL body) | yes |
| success then register | yes |
| failure does not register | yes |
| checksum conflict → `MIGRATION_CHECKSUM_MISMATCH` | yes |
| baseline_1_0_5 valid | yes |
| 001–005 continuous on create_db / apply | yes |
| re-run idempotent | yes |
| old AnalysisRun readable | yes (`subject_type` / `subject_id` preserved) |
| 003 error columns present | yes |

## Schema correction note

`error_code` / `error_message` were added by revising `SQL_003` **without** a new migration_id (Phase 1A not released). Fresh DBs create columns; existing Agent A tables get idempotent `ALTER TABLE ... ADD COLUMN`.
